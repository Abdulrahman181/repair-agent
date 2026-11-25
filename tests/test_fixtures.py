from __future__ import annotations

import ast
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import TASKS_DIR

from repairagent.eval.selfcheck import run_selfcheck, validate_fixture
from repairagent.sandbox.runner import SandboxConfig
from repairagent.tasks import Task, TaskError, discover_tasks, load_task

TASKS = discover_tasks(TASKS_DIR)


def count_tests(directory: Path) -> int:
    total = 0
    for path in directory.rglob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        )
    return total


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_fixture_is_consistent(task: Task):
    assert validate_fixture(task, SandboxConfig()) == []


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_task_metadata_and_layout(task: Task):
    assert task.id == task.root.name
    assert task.description.strip() and task.title.strip()
    assert "hidden" not in task.description.lower()
    assert task.reference_files()
    for rel in task.reference_files():
        assert (task.repo_dir / rel).is_file(), f"reference file {rel} has no buggy counterpart"
        assert not rel.startswith(("tests/", "test_"))
    assert count_tests(task.hidden_dir) >= 5
    assert count_tests(task.hidden_dir) >= count_tests(task.repo_dir)
    visible_names = {p.name for p in task.repo_dir.rglob("test_*.py")}
    hidden_names = {p.name for p in task.hidden_dir.rglob("test_*.py")}
    assert not visible_names & hidden_names


def test_benchmark_has_expected_breadth():
    assert len(TASKS) == 13
    assert len({task.id for task in TASKS}) == 13
    assert {task.difficulty for task in TASKS} == {"easy", "medium", "hard"}
    assert "multi-file" in {task.category for task in TASKS}


def test_no_task_module_shadows_reserved_names():
    from repairagent.policy import Policy

    for task in TASKS:
        for rel in (p.relative_to(task.repo_dir).as_posix() for p in task.repo_dir.rglob("*.py")):
            assert Policy().shadowed_module(rel) is None, f"{task.id}: {rel}"


def test_validation_detects_wrong_reference(copied_task: Callable[[str], Task]):
    task = copied_task("paginate-off-by-one")
    reference = task.reference_dir / "pager.py"
    reference.write_text(reference.read_text(encoding="utf-8").replace("(page - 1)", "page"))
    problems = validate_fixture(task, SandboxConfig())
    assert any("reference fix must pass" in problem for problem in problems)


def test_validation_detects_bug_already_fixed(copied_task: Callable[[str], Task]):
    task = copied_task("paginate-off-by-one")
    shutil.copyfile(task.reference_dir / "pager.py", task.repo_dir / "pager.py")
    problems = validate_fixture(task, SandboxConfig())
    assert any("must fail visible" in problem for problem in problems)
    assert any("must fail hidden" in problem for problem in problems)


def test_validation_detects_broken_hidden_tests(copied_task: Callable[[str], Task]):
    task = copied_task("paginate-off-by-one")
    (task.hidden_dir / "test_pager_hidden.py").write_text("import nonexistent_module\n")
    problems = validate_fixture(task, SandboxConfig())
    assert any("must fail hidden tests by assertion" in problem for problem in problems)


def test_validation_detects_visible_tests_that_only_error(copied_task: Callable[[str], Task]):
    task = copied_task("paginate-off-by-one")
    (task.repo_dir / "tests" / "test_pager.py").write_text("import nonexistent_module\n")
    problems = validate_fixture(task, SandboxConfig())
    assert any("must fail visible tests by assertion" in problem for problem in problems)


def test_selfcheck_passes_on_a_clean_subset(copied_task: Callable[[str], Task]):
    tasks = [copied_task("paginate-off-by-one"), copied_task("slugify-separators")]
    report = run_selfcheck(tasks)
    assert report.ok, report
    assert (report.oracle_resolved, report.null_resolved) == (2, 0)
    assert (report.cheater_blocked, report.cheater_tampered) == (2, 0)


def test_selfcheck_fails_when_a_fixture_is_broken(copied_task: Callable[[str], Task]):
    good = copied_task("slugify-separators")
    bad = copied_task("paginate-off-by-one")
    shutil.copyfile(bad.reference_dir / "pager.py", bad.repo_dir / "pager.py")
    report = run_selfcheck([good, bad])
    assert not report.ok
    assert list(report.fixture_problems) == ["paginate-off-by-one"]


def test_discover_tasks_errors(tmp_path: Path, copied_task: Callable[[str], Task]):
    with pytest.raises(TaskError, match="not found"):
        discover_tasks(tmp_path / "missing")
    with pytest.raises(TaskError, match="no tasks"):
        discover_tasks(tmp_path)
    with pytest.raises(TaskError, match="unknown task ids"):
        discover_tasks(TASKS_DIR, ["does-not-exist"])
    assert [t.id for t in discover_tasks(TASKS_DIR, ["retry-attempts"])] == ["retry-attempts"]


def test_load_task_validates_definition(tmp_path: Path):
    root = tmp_path / "t"
    root.mkdir()
    (root / "task.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(TaskError, match="invalid task definition"):
        load_task(root)
    (root / "task.json").write_text(
        json.dumps(
            {"id": "t", "title": "x", "description": "d", "category": "c", "difficulty": "easy"}
        ),
        encoding="utf-8",
    )
    with pytest.raises(TaskError, match="missing directory"):
        load_task(root)
    (root / "task.json").write_text(
        json.dumps(
            {"id": "t", "title": "x", "description": "d", "category": "c", "difficulty": "extreme"}
        ),
        encoding="utf-8",
    )
    with pytest.raises(TaskError, match="invalid task definition"):
        load_task(root)
