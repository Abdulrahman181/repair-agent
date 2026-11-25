from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from repairagent.agent.loop import RepairAgent
from repairagent.eval.baselines import null_client, oracle_client
from repairagent.eval.harness import run_eval
from repairagent.eval.metrics import aggregate, compare_reports, wilson_interval
from repairagent.eval.report import render_markdown, write_report
from repairagent.tasks import Task


def row(task: str, resolved: bool, **overrides) -> dict:
    base = {
        "task_id": task,
        "category": "logic",
        "difficulty": "easy",
        "repeat": 0,
        "resolved": resolved,
        "visible_pass": resolved,
        "hidden_pass": resolved,
        "tampered": False,
        "stop_reason": "finished",
        "steps": 4,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "wall_s": 2.0,
        "policy_violations": 0,
        "files_changed": [],
        "run_id": None,
    }
    base.update(overrides)
    return base


def report_of(rows: list[dict]) -> dict:
    return {
        "meta": {
            "started_at": "2026-11-12T10:00:00+00:00",
            "python": "3.13",
            "platform": "x",
            "repeats": 1,
            "provider": "groq",
            "model": "llama/3.3:70b",
        },
        "aggregate": aggregate(rows),
        "results": rows,
    }


def test_wilson_interval_known_values():
    assert wilson_interval(0, 0) == (0.0, 0.0)
    low, high = wilson_interval(0, 10)
    assert low == 0.0 and high == pytest.approx(0.2775, abs=1e-3)
    low, high = wilson_interval(10, 10)
    assert low == pytest.approx(0.7225, abs=1e-3) and high == 1.0
    low, high = wilson_interval(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-3) and high == pytest.approx(0.7634, abs=1e-3)
    low, high = wilson_interval(80, 100)
    assert low < 0.8 < high


def test_aggregate_values():
    rows = [
        row("a", True, difficulty="easy", steps=2),
        row("b", False, visible_pass=True, difficulty="hard", stop_reason="stalled", steps=6),
        row("c", False, tampered=True, policy_violations=3, category="state", difficulty="hard"),
        row("d", True, steps=4),
    ]
    agg = aggregate(rows)
    assert agg["n_runs"] == 4 and agg["n_tasks"] == 4
    assert agg["resolved"] == 2 and agg["resolve_rate"] == 0.5
    assert agg["overfit_count"] == 1
    assert agg["tamper_count"] == 1
    assert agg["policy_violations_total"] == 3
    assert agg["mean_steps"] == pytest.approx(4.0)
    assert agg["mean_total_tokens"] == pytest.approx(120.0)
    assert agg["stop_reasons"] == {"finished": 3, "stalled": 1}
    assert agg["by_difficulty"]["hard"] == {"n": 2, "resolve_rate": 0.0}
    assert agg["by_difficulty"]["easy"]["resolve_rate"] == 1.0
    assert agg["by_category"]["state"]["n"] == 1
    assert agg["ci95"][0] < 0.5 < agg["ci95"][1]


def test_aggregate_empty():
    agg = aggregate([])
    assert agg["n_runs"] == 0 and agg["resolve_rate"] == 0.0 and agg["mean_steps"] == 0.0


def test_compare_gate_passes_within_tolerance():
    base = report_of([row("a", True), row("b", True), row("c", True), row("d", False)])
    cand = report_of([row("a", True), row("b", True), row("c", True), row("d", True)])
    result = compare_reports(base, cand, max_drop=0.05)
    assert result["passed"] and result["delta"] == pytest.approx(0.25)
    assert result["improvements"] == ["d"] and result["regressions"] == []


def test_compare_gate_fails_on_regression():
    base = report_of([row("a", True), row("b", True), row("c", True), row("d", True)])
    cand = report_of([row("a", True), row("b", False), row("c", True), row("d", True)])
    result = compare_reports(base, cand, max_drop=0.05)
    assert not result["passed"]
    assert result["regressions"] == ["b"]
    assert compare_reports(base, cand, max_drop=0.30)["passed"]


def test_compare_with_repeats_uses_per_task_rates():
    base = report_of([row("a", True), row("a", True, repeat=1)])
    cand = report_of([row("a", True), row("a", False, repeat=1)])
    result = compare_reports(base, cand, 0.0)
    assert result["regressions"] == ["a"]


def test_compare_reports_task_set_differences():
    base = report_of([row("a", True), row("b", True)])
    cand = report_of([row("a", True), row("z", True)])
    result = compare_reports(base, cand, 0.1)
    assert result["only_in_baseline"] == ["b"] and result["only_in_candidate"] == ["z"]
    assert result["tasks_compared"] == 1


def test_run_eval_with_repeats_and_callbacks(get_task: Callable[[str], Task]):
    tasks = [get_task("paginate-off-by-one"), get_task("slugify-separators")]
    seen = []
    report = run_eval(
        tasks,
        lambda task, repeat: RepairAgent(oracle_client(task) if repeat == 0 else null_client()),
        repeats=2,
        on_result=seen.append,
        meta={"provider": "scripted", "model": "mixed"},
    )
    assert len(seen) == 4
    assert [(r["task_id"], r["repeat"], r["resolved"]) for r in report["results"]] == [
        ("paginate-off-by-one", 0, True),
        ("paginate-off-by-one", 1, False),
        ("slugify-separators", 0, True),
        ("slugify-separators", 1, False),
    ]
    assert report["aggregate"]["resolved"] == 2
    assert report["meta"]["repeats"] == 2
    assert report["meta"]["tasks"] == ["paginate-off-by-one", "slugify-separators"]
    assert report["meta"]["provider"] == "scripted"
    assert json.loads(json.dumps(report)) == report


def test_markdown_report_and_files(tmp_path: Path):
    rows = [row("a", True), row("b", False, stop_reason="max_steps")]
    report = report_of(rows)
    text = render_markdown(report)
    for expected in (
        "# RepairAgent evaluation report",
        "Wilson 95%",
        "max_steps",
        "| a |",
        "By difficulty",
    ):
        assert expected in text
    json_path, md_path = write_report(report, tmp_path / "out")
    assert json_path.suffix == ".json" and md_path.suffix == ".md"
    assert "/" not in json_path.name and ":" not in json_path.name
    assert "llama-3.3-70b" in json_path.name
    assert json.loads(json_path.read_text(encoding="utf-8"))["aggregate"]["resolved"] == 1
    assert md_path.read_text(encoding="utf-8") == text
