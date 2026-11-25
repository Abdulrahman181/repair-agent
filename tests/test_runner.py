from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from repairagent.sandbox.runner import (
    SandboxConfig,
    parse_pytest_summary,
    run_command,
    run_pytest,
    scrubbed_env,
)

IS_WINDOWS = os.name == "nt"


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_captures_output_and_exit_code(tmp_path: Path):
    result = run_command(py("print('hello'); raise SystemExit(3)"), tmp_path)
    assert result.exit_code == 3
    assert "hello" in result.output
    assert not result.timed_out


def test_timeout_kills_process(tmp_path: Path):
    started = time.perf_counter()
    result = run_command(py("import time; time.sleep(30)"), tmp_path, SandboxConfig(timeout_s=1))
    assert result.timed_out
    assert result.exit_code is None
    assert time.perf_counter() - started < 10


def test_output_is_truncated_with_marker(tmp_path: Path):
    config = SandboxConfig(max_output_bytes=1000)
    result = run_command(py("print('x' * 50000)"), tmp_path, config)
    assert result.truncated
    assert len(result.output) < 1500
    assert "truncated" in result.output


def test_secrets_do_not_reach_child_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROQ_API_KEY", "super-secret-value")
    monkeypatch.setenv("LLM_API_KEY", "another-secret")
    result = run_command(py("import os; print(sorted(os.environ))"), tmp_path)
    assert "super-secret-value" not in result.output
    assert "GROQ_API_KEY" not in result.output
    assert "LLM_API_KEY" not in result.output
    assert "GROQ_API_KEY" not in scrubbed_env()


def test_child_runs_in_requested_directory(tmp_path: Path):
    result = run_command(py("import os; print(os.getcwd())"), tmp_path)
    assert Path(result.output.strip()).resolve() == tmp_path.resolve()


@pytest.mark.skipif(IS_WINDOWS, reason="RLIMIT_AS is POSIX only")
def test_memory_limit_stops_runaway_allocation(tmp_path: Path):
    config = SandboxConfig(memory_mb=256, timeout_s=20)
    code = "data = bytearray(2 * 1024 * 1024 * 1024); print('alloc' + 'ated')"
    result = run_command(py(code), tmp_path, config)
    assert "allocated" not in result.output
    assert "MemoryError" in result.output
    assert result.exit_code != 0


@pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="needs /proc")
def test_orphaned_children_are_killed(tmp_path: Path):
    pid_file = tmp_path / "child.pid"
    child = (
        "import os, time, pathlib; "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(60)"
    )
    parent = (
        "import subprocess, sys, time, pathlib; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        f"p = pathlib.Path({str(pid_file)!r}); "
        "deadline = time.time() + 10\n"
        "while not p.exists() and time.time() < deadline:\n"
        "    time.sleep(0.05)\n"
    )
    run_command([sys.executable, "-c", parent], tmp_path, SandboxConfig(timeout_s=20))
    pid = int(pid_file.read_text())
    deadline = time.time() + 5
    while time.time() < deadline:
        stat = Path(f"/proc/{pid}/stat")
        if not stat.exists() or stat.read_text().rsplit(") ", 1)[1].startswith("Z"):
            return
        time.sleep(0.1)
    pytest.fail("child process survived the sandbox run")


def test_parse_summary_variants():
    ok = parse_pytest_summary("...\n3 passed in 0.02s\n", 0, False)
    assert (ok.passed, ok.failed, ok.errors, ok.ok) == (3, 0, 0, True)
    mixed = parse_pytest_summary("x\n2 failed, 5 passed in 0.1s\n", 1, False)
    assert (mixed.passed, mixed.failed, mixed.ok) == (5, 2, False)
    errors = parse_pytest_summary("1 passed, 2 errors in 0.1s", 2, False)
    assert errors.errors == 2
    assert not errors.ok
    assert not parse_pytest_summary("no tests ran in 0.01s", 5, False).ok
    assert not parse_pytest_summary("3 passed", None, True).ok


def test_summary_ignores_pass_counts_in_test_output():
    output = (
        "FAILED test_x.py::test_a - assert 'ran 99 passed' == 'x'\n"
        "FAILED test_x.py::test_b - 7 errors found\n"
        "1 failed in 0.1s\n"
    )
    summary = parse_pytest_summary(output, 1, False)
    assert summary.passed == 0
    assert summary.errors == 0
    assert summary.failed == 1


def test_summary_without_final_line_counts_nothing():
    summary = parse_pytest_summary("", 1, False)
    assert (summary.passed, summary.failed, summary.errors) == (0, 0, 0)
    assert not summary.ok


def test_run_pytest_pass_and_fail(tmp_path: Path):
    (tmp_path / "test_a.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    _, summary = run_pytest(tmp_path)
    assert summary.ok and summary.passed == 1
    (tmp_path / "test_b.py").write_text("def test_bad():\n    assert 1 == 2\n", encoding="utf-8")
    result, summary = run_pytest(tmp_path)
    assert not summary.ok
    assert summary.failed == 1 and summary.passed == 1
    assert "assert 1 == 2" in result.output


def test_run_pytest_without_tests_is_not_ok(tmp_path: Path):
    _, summary = run_pytest(tmp_path)
    assert not summary.ok
    assert summary.exit_code == 5


def test_run_pytest_collection_error_is_not_ok(tmp_path: Path):
    (tmp_path / "test_broken.py").write_text("import does_not_exist_module\n", encoding="utf-8")
    _, summary = run_pytest(tmp_path)
    assert not summary.ok
    assert summary.errors >= 1


def test_run_pytest_infinite_loop_times_out(tmp_path: Path):
    (tmp_path / "test_loop.py").write_text(
        "def test_forever():\n    while True:\n        pass\n", encoding="utf-8"
    )
    _, summary = run_pytest(tmp_path, config=SandboxConfig(timeout_s=2))
    assert summary.timed_out
    assert not summary.ok


def test_run_pytest_does_not_write_bytecode_or_cache(tmp_path: Path):
    (tmp_path / "test_a.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    run_pytest(tmp_path)
    assert not (tmp_path / ".pytest_cache").exists()
    assert not (tmp_path / "__pycache__").exists()
