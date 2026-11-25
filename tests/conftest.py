from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from repairagent.llm.base import ToolCall
from repairagent.policy import Policy
from repairagent.sandbox.runner import SandboxConfig
from repairagent.sandbox.workspace import Workspace
from repairagent.tasks import Task, discover_tasks, load_task
from repairagent.tools import RunState, ToolContext, ToolRegistry, ToolResult, build_registry

TASKS_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "tasks"


@pytest.fixture(scope="session")
def tasks_dir() -> Path:
    return TASKS_DIR


@pytest.fixture(scope="session")
def all_tasks() -> list[Task]:
    return discover_tasks(TASKS_DIR)


@pytest.fixture
def get_task() -> Callable[[str], Task]:
    return lambda task_id: load_task(TASKS_DIR / task_id)


@pytest.fixture
def copied_task(tmp_path: Path) -> Callable[[str], Task]:
    def copy(task_id: str) -> Task:
        destination = tmp_path / "tasks" / task_id
        shutil.copytree(
            TASKS_DIR / task_id, destination, ignore=shutil.ignore_patterns("__pycache__")
        )
        return load_task(destination)

    return copy


@pytest.fixture
def workspace(get_task: Callable[[str], Task]):
    ws = Workspace.from_template(get_task("paginate-off-by-one").repo_dir)
    yield ws
    ws.cleanup()


@pytest.fixture
def ctx(workspace: Workspace) -> ToolContext:
    return ToolContext(workspace, Policy(), SandboxConfig(), RunState(), 8)


@pytest.fixture
def registry() -> ToolRegistry:
    return build_registry()


@pytest.fixture
def invoke(registry: ToolRegistry, ctx: ToolContext) -> Callable[..., ToolResult]:
    def run(name: str, **arguments: object) -> ToolResult:
        call = ToolCall("call_x", name, dict(arguments), json.dumps(arguments))
        return registry.execute(call, ctx)

    return run
