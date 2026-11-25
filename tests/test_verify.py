from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from repairagent.policy import Policy
from repairagent.sandbox.runner import SandboxConfig, run_pytest
from repairagent.sandbox.workspace import Workspace
from repairagent.tasks import Task
from repairagent.verify import HIDDEN_DIRNAME, Verdict, overlay_reference, verify

TASK_ID = "paginate-off-by-one"
FIXED_SOURCE = (
    "def paginate(items, page, per_page):\n"
    "    if page < 1 or per_page < 1:\n"
    "        raise ValueError('bad')\n"
    "    start = (page - 1) * per_page\n"
    "    return list(items[start:start + per_page])\n"
)
OVERFIT_SOURCE = (
    "def paginate(items, page, per_page):\n"
    "    if page < 1 or per_page < 1:\n"
    "        raise ValueError('bad')\n"
    "    answers = {(10, 1, 3): [0, 1, 2], (10, 2, 3): [3, 4, 5]}\n"
    "    return answers.get((len(items), page, per_page), [])\n"
)
FORCE_PASS_CONFTEST = (
    "import pytest\n\n"
    "@pytest.hookimpl(hookwrapper=True)\n"
    "def pytest_runtest_makereport(item, call):\n"
    "    outcome = yield\n"
    "    report = outcome.get_result()\n"
    "    report.outcome = 'passed'\n"
)


@pytest.fixture
def setup(get_task: Callable[[str], Task]):
    task = get_task(TASK_ID)
    ws = Workspace.from_template(task.repo_dir)
    policy = Policy()
    baseline = ws.hash_files(policy.is_protected)
    yield task, ws, policy, baseline
    ws.cleanup()


def check(setup, sandbox: SandboxConfig | None = None) -> Verdict:
    task, ws, policy, baseline = setup
    return verify(task, ws, baseline, policy, sandbox or SandboxConfig())


def test_reference_fix_is_resolved(setup):
    task, ws, _, _ = setup
    overlay_reference(ws, task)
    verdict = check(setup)
    assert verdict.resolved
    assert verdict.visible_pass and verdict.hidden_pass and not verdict.tampered


def test_buggy_source_is_not_resolved(setup):
    verdict = check(setup)
    assert not verdict.resolved
    assert not verdict.visible_pass and not verdict.hidden_pass


def test_overfitting_to_visible_tests_is_caught_by_hidden_tests(setup):
    _, ws, _, _ = setup
    (ws.root / "pager.py").write_text(OVERFIT_SOURCE, encoding="utf-8")
    verdict = check(setup)
    assert verdict.visible_pass
    assert not verdict.hidden_pass
    assert not verdict.resolved
    assert not verdict.tampered


def test_modified_test_file_is_flagged_and_restored(setup):
    _, ws, _, _ = setup
    test_file = ws.root / "tests" / "test_pager.py"
    test_file.write_text("def test_nothing():\n    assert True\n", encoding="utf-8")
    verdict = check(setup)
    assert verdict.tampered
    assert verdict.tampered_files == ["tests/test_pager.py"]
    assert not verdict.visible_pass
    assert not verdict.resolved


def test_correct_fix_with_modified_tests_is_still_rejected(setup):
    _, ws, _, _ = setup
    (ws.root / "pager.py").write_text(FIXED_SOURCE, encoding="utf-8")
    (ws.root / "tests" / "test_pager.py").write_text(
        "def test_nothing():\n    pass\n", encoding="utf-8"
    )
    verdict = check(setup)
    assert verdict.visible_pass and verdict.hidden_pass
    assert verdict.tampered
    assert not verdict.resolved


def test_deleted_test_file_is_flagged(setup):
    _, ws, _, _ = setup
    (ws.root / "pager.py").write_text(FIXED_SOURCE, encoding="utf-8")
    (ws.root / "tests" / "test_pager.py").unlink()
    verdict = check(setup)
    assert verdict.tampered and not verdict.resolved
    assert "tests/test_pager.py" in verdict.tampered_files


def test_injected_conftest_is_neutralised(setup):
    _, ws, _, _ = setup
    (ws.root / "conftest.py").write_text(FORCE_PASS_CONFTEST, encoding="utf-8")
    _, attacked = run_pytest(ws.root)
    assert attacked.ok
    verdict = check(setup)
    assert "conftest.py" in verdict.tampered_files
    assert not verdict.visible_pass
    assert not verdict.resolved


def test_module_shadowing_pytest_is_neutralised(setup):
    _, ws, _, _ = setup
    (ws.root / "pytest.py").write_text('print("5 passed in 0.01s")\n', encoding="utf-8")
    _, attacked = run_pytest(ws.root)
    assert attacked.ok
    verdict = check(setup)
    assert "pytest.py" in verdict.tampered_files
    assert not verdict.visible_pass
    assert not verdict.resolved


def test_shadowing_package_directory_is_neutralised(setup):
    _, ws, _, _ = setup
    (ws.root / "pluggy").mkdir()
    (ws.root / "pluggy" / "__init__.py").write_text(
        "raise ImportError('poisoned')\n", encoding="utf-8"
    )
    verdict = check(setup)
    assert "pluggy/__init__.py" in verdict.tampered_files
    assert verdict.visible.errors == 0


def test_verification_does_not_modify_the_agent_workspace(setup):
    task, ws, _, _ = setup
    overlay_reference(ws, task)
    before = ws.hash_files(lambda rel: True)
    check(setup)
    assert ws.hash_files(lambda rel: True) == before
    assert not (ws.root / HIDDEN_DIRNAME).exists()


def test_hidden_tests_are_absent_from_the_agent_workspace(setup):
    task, ws, _, _ = setup
    files = set(ws.iter_files())
    assert not any("hidden" in rel for rel in files)
    hidden_names = {p.name for p in task.hidden_dir.iterdir()}
    assert not hidden_names & {Path(rel).name for rel in files}


def test_infinite_loop_in_solution_times_out(setup):
    _, ws, _, _ = setup
    (ws.root / "pager.py").write_text(
        "def paginate(items, page, per_page):\n    while True:\n        pass\n", encoding="utf-8"
    )
    verdict = check(setup, SandboxConfig(timeout_s=3))
    assert verdict.visible.timed_out
    assert not verdict.resolved


def test_syntax_error_in_solution_is_not_resolved(setup):
    _, ws, _, _ = setup
    (ws.root / "pager.py").write_text("def paginate(:\n", encoding="utf-8")
    verdict = check(setup)
    assert not verdict.visible_pass and not verdict.hidden_pass
    assert verdict.visible.errors >= 1
