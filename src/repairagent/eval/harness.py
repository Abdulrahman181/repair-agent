from __future__ import annotations

import platform
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from repairagent import __version__
from repairagent.agent.loop import AgentRunResult, RepairAgent
from repairagent.eval.metrics import aggregate
from repairagent.tasks import Task

AgentFactory = Callable[[Task, int], RepairAgent]
ResultCallback = Callable[["TaskResult"], None]


@dataclass
class TaskResult:
    task_id: str
    category: str
    difficulty: str
    repeat: int
    resolved: bool
    visible_pass: bool
    hidden_pass: bool
    tampered: bool
    stop_reason: str
    steps: int
    prompt_tokens: int
    completion_tokens: int
    wall_s: float
    policy_violations: int
    files_changed: list[str]
    run_id: int | None

    @classmethod
    def from_outcome(cls, task: Task, repeat: int, outcome: AgentRunResult) -> TaskResult:
        verdict = outcome.verdict
        return cls(
            task_id=task.id,
            category=task.category,
            difficulty=task.difficulty,
            repeat=repeat,
            resolved=verdict.resolved,
            visible_pass=verdict.visible_pass,
            hidden_pass=verdict.hidden_pass,
            tampered=verdict.tampered,
            stop_reason=outcome.stop_reason,
            steps=outcome.steps,
            prompt_tokens=outcome.prompt_tokens,
            completion_tokens=outcome.completion_tokens,
            wall_s=round(outcome.wall_s, 3),
            policy_violations=outcome.policy_violations,
            files_changed=outcome.files_changed,
            run_id=outcome.run_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_eval(
    tasks: Sequence[Task],
    agent_factory: AgentFactory,
    repeats: int = 1,
    on_result: ResultCallback | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = datetime.now(UTC).isoformat(timespec="seconds")
    results: list[TaskResult] = []
    for task in tasks:
        for repeat in range(repeats):
            outcome = agent_factory(task, repeat).run(task)
            record = TaskResult.from_outcome(task, repeat, outcome)
            results.append(record)
            if on_result is not None:
                on_result(record)
    rows = [record.to_dict() for record in results]
    return {
        "schema_version": 1,
        "meta": {
            **(meta or {}),
            "started_at": started,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "repairagent": __version__,
            "tasks": [task.id for task in tasks],
            "repeats": repeats,
        },
        "aggregate": aggregate(rows),
        "results": rows,
    }
