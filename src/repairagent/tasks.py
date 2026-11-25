from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError


class TaskError(Exception):
    pass


class TaskSpec(BaseModel):
    id: str
    title: str
    description: str
    category: str
    difficulty: Literal["easy", "medium", "hard"]


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    description: str
    category: str
    difficulty: str
    root: Path

    @property
    def repo_dir(self) -> Path:
        return self.root / "repo"

    @property
    def hidden_dir(self) -> Path:
        return self.root / "hidden"

    @property
    def reference_dir(self) -> Path:
        return self.root / "reference"

    def reference_files(self) -> list[str]:
        return sorted(
            path.relative_to(self.reference_dir).as_posix()
            for path in self.reference_dir.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )


def load_task(root: Path) -> Task:
    spec_path = root / "task.json"
    try:
        spec = TaskSpec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        raise TaskError(f"invalid task definition at {spec_path}: {exc}") from exc
    task = Task(spec.id, spec.title, spec.description, spec.category, spec.difficulty, root)
    for required in (task.repo_dir, task.hidden_dir, task.reference_dir):
        if not required.is_dir():
            raise TaskError(f"task '{spec.id}' is missing directory '{required.name}'")
    return task


def discover_tasks(tasks_dir: Path, only: Sequence[str] | None = None) -> list[Task]:
    if not tasks_dir.is_dir():
        raise TaskError(f"tasks directory not found: {tasks_dir}")
    tasks = [
        load_task(path)
        for path in sorted(tasks_dir.iterdir())
        if path.is_dir() and (path / "task.json").is_file()
    ]
    if only:
        wanted = set(only)
        known = {task.id for task in tasks}
        missing = sorted(wanted - known)
        if missing:
            raise TaskError(f"unknown task ids: {', '.join(missing)}")
        tasks = [task for task in tasks if task.id in wanted]
    if not tasks:
        raise TaskError(f"no tasks found in {tasks_dir}")
    return tasks


def default_tasks_dir() -> Path:
    configured = os.environ.get("REPAIRAGENT_TASKS_DIR")
    if configured:
        return Path(configured)
    local = Path("benchmarks") / "tasks"
    if local.is_dir():
        return local
    return Path(__file__).resolve().parents[2] / "benchmarks" / "tasks"
