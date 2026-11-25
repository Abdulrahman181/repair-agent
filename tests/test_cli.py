from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import TASKS_DIR
from typer.testing import CliRunner

import repairagent.cli as cli
from repairagent.eval.metrics import aggregate
from repairagent.llm import ScriptedClient, tool_call_response
from repairagent.store import RunStore

runner = CliRunner()

FIX_SCRIPT = [
    (
        "replace_in_file",
        {
            "path": "pager.py",
            "old": "start = page * per_page",
            "new": "start = (page - 1) * per_page",
        },
    ),
    ("run_tests", {}),
    ("finish", {"summary": "fixed"}),
]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    for name in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "GROQ_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def make_report(path: Path, resolved_flags: list[bool]) -> None:
    rows = [
        {
            "task_id": f"t{i}",
            "category": "c",
            "difficulty": "easy",
            "repeat": 0,
            "resolved": flag,
            "visible_pass": flag,
            "hidden_pass": flag,
            "tampered": False,
            "stop_reason": "finished",
            "steps": 1,
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "wall_s": 1.0,
            "policy_violations": 0,
            "files_changed": [],
            "run_id": None,
        }
        for i, flag in enumerate(resolved_flags)
    ]
    path.write_text(json.dumps({"results": rows, "aggregate": aggregate(rows)}), encoding="utf-8")


def test_tasks_command_lists_all_tasks():
    result = runner.invoke(cli.app, ["tasks", "--tasks-dir", str(TASKS_DIR)])
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 13
    assert any("cart-discount-pricing" in line and "multi-file" in line for line in lines)


def test_tasks_command_reports_missing_directory(tmp_path: Path):
    result = runner.invoke(cli.app, ["tasks", "--tasks-dir", str(tmp_path / "nope")])
    assert result.exit_code == 2
    assert "tasks directory not found" in result.output


def test_run_requires_model_and_key():
    result = runner.invoke(cli.app, ["run", "paginate-off-by-one", "--tasks-dir", str(TASKS_DIR)])
    assert result.exit_code == 2
    assert "No model configured" in result.output


def test_run_requires_api_key_for_groq():
    args = ["run", "paginate-off-by-one", "--model", "m", "--tasks-dir", str(TASKS_DIR)]
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 2
    assert "GROQ_API_KEY" in result.output


def test_run_rejects_unknown_task():
    args = ["run", "nope", "--provider", "ollama", "--model", "m", "--tasks-dir", str(TASKS_DIR)]
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 2
    assert "unknown task ids" in result.output


def test_eval_and_trace_end_to_end_with_scripted_llm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    def fake_client(_settings):
        return ScriptedClient(
            [tool_call_response(name, args, f"c{i}") for i, (name, args) in enumerate(FIX_SCRIPT)]
        )

    monkeypatch.setattr(cli, "OpenAICompatClient", fake_client)
    db = tmp_path / "runs.db"
    out = tmp_path / "reports"
    args = [
        "eval",
        "--task",
        "paginate-off-by-one",
        "--provider",
        "ollama",
        "--model",
        "scripted-1",
        "--out",
        str(out),
        "--db",
        str(db),
        "--tasks-dir",
        str(TASKS_DIR),
    ]
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    assert "[PASS] paginate-off-by-one" in result.output
    assert "resolved 1/1 (100.0%)" in result.output
    reports = sorted(out.glob("*.json"))
    assert len(reports) == 1 and sorted(out.glob("*.md"))
    data = json.loads(reports[0].read_text(encoding="utf-8"))
    assert data["meta"]["model"] == "scripted-1"
    run_id = data["results"][0]["run_id"]
    traced = runner.invoke(cli.app, ["trace", str(run_id), "--db", str(db)])
    assert traced.exit_code == 0
    assert "resolved=1" in traced.output
    assert "replace_in_file" in traced.output and "finish" in traced.output


def test_run_command_prints_outcome(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(
        cli,
        "OpenAICompatClient",
        lambda _settings: ScriptedClient(
            [tool_call_response(n, a, f"c{i}") for i, (n, a) in enumerate(FIX_SCRIPT)]
        ),
    )
    args = [
        "run",
        "paginate-off-by-one",
        "--provider",
        "ollama",
        "--model",
        "m",
        "--db",
        str(tmp_path / "r.db"),
        "--tasks-dir",
        str(TASKS_DIR),
    ]
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    assert "resolved     : True" in result.output
    assert "files changed: pager.py" in result.output


def test_trace_errors(tmp_path: Path):
    missing_db = runner.invoke(cli.app, ["trace", "1", "--db", str(tmp_path / "none.db")])
    assert missing_db.exit_code == 2
    db = tmp_path / "runs.db"
    RunStore(db).close()
    missing_run = runner.invoke(cli.app, ["trace", "5", "--db", str(db)])
    assert missing_run.exit_code == 2 and "not found" in missing_run.output


def test_compare_gate_exit_codes(tmp_path: Path):
    base, good, bad = tmp_path / "b.json", tmp_path / "g.json", tmp_path / "x.json"
    make_report(base, [True, True, True, True])
    make_report(good, [True, True, True, True])
    make_report(bad, [True, False, False, True])
    passed = runner.invoke(cli.app, ["compare", str(base), str(good)])
    assert passed.exit_code == 0 and "GATE PASSED" in passed.output
    failed = runner.invoke(cli.app, ["compare", str(base), str(bad)])
    assert failed.exit_code == 1 and "GATE FAILED" in failed.output
    assert "t1, t2" in failed.output
    relaxed = runner.invoke(cli.app, ["compare", str(base), str(bad), "--max-drop", "0.6"])
    assert relaxed.exit_code == 0


def test_compare_unreadable_report(tmp_path: Path):
    result = runner.invoke(cli.app, ["compare", str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    assert result.exit_code == 2 and "could not read" in result.output


def test_selfcheck_command_on_subset(tmp_path: Path):
    subset = tmp_path / "subset"
    for task_id in ("paginate-off-by-one", "slugify-separators"):
        shutil.copytree(
            TASKS_DIR / task_id, subset / task_id, ignore=shutil.ignore_patterns("__pycache__")
        )
    result = runner.invoke(cli.app, ["selfcheck", "--tasks-dir", str(subset)])
    assert result.exit_code == 0, result.output
    assert "SELFCHECK PASSED" in result.output
    assert "oracle agent resolved : 2/2" in result.output
    assert "null agent resolved   : 0/2" in result.output


def test_selfcheck_command_reports_broken_fixture(tmp_path: Path):
    subset = tmp_path / "subset"
    shutil.copytree(
        TASKS_DIR / "paginate-off-by-one",
        subset / "paginate-off-by-one",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copyfile(
        subset / "paginate-off-by-one" / "reference" / "pager.py",
        subset / "paginate-off-by-one" / "repo" / "pager.py",
    )
    result = runner.invoke(cli.app, ["selfcheck", "--tasks-dir", str(subset)])
    assert result.exit_code == 1
    assert "FIXTURE PROBLEM" in result.output
