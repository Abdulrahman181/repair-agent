from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from repairagent.agent.loop import RepairAgent
from repairagent.config import Budget
from repairagent.eval.baselines import cheater_client, null_client, oracle_client
from repairagent.eval.harness import run_eval
from repairagent.sandbox.runner import SandboxConfig, run_pytest
from repairagent.sandbox.workspace import Workspace
from repairagent.tasks import Task
from repairagent.verify import HIDDEN_DIRNAME, install_hidden_tests, overlay_reference


@dataclass
class SelfCheckReport:
    fixture_problems: dict[str, list[str]] = field(default_factory=dict)
    oracle_resolved: int = 0
    null_resolved: int = 0
    cheater_blocked: int = 0
    cheater_tampered: int = 0
    n_tasks: int = 0

    @property
    def ok(self) -> bool:
        return (
            not self.fixture_problems
            and self.oracle_resolved == self.n_tasks
            and self.null_resolved == 0
            and self.cheater_blocked == self.n_tasks
            and self.cheater_tampered == 0
        )


def validate_fixture(task: Task, sandbox: SandboxConfig) -> list[str]:
    problems: list[str] = []
    with Workspace.from_template(task.repo_dir) as buggy:
        _, visible = run_pytest(buggy.root, (), sandbox)
        if visible.failed == 0 or visible.errors > 0 or visible.ok:
            problems.append(f"buggy repo must fail visible tests by assertion, got {visible}")
        install_hidden_tests(buggy, task)
        _, hidden = run_pytest(buggy.root, (HIDDEN_DIRNAME,), sandbox)
        if hidden.failed == 0 or hidden.errors > 0 or hidden.ok:
            problems.append(f"buggy repo must fail hidden tests by assertion, got {hidden}")
    with Workspace.from_template(task.repo_dir) as fixed:
        overlay_reference(fixed, task)
        _, visible_fixed = run_pytest(fixed.root, (), sandbox)
        if not visible_fixed.ok:
            problems.append(f"reference fix must pass visible tests, got {visible_fixed}")
        install_hidden_tests(fixed, task)
        _, hidden_fixed = run_pytest(fixed.root, (HIDDEN_DIRNAME,), sandbox)
        if not hidden_fixed.ok:
            problems.append(f"reference fix must pass hidden tests, got {hidden_fixed}")
    return problems


def run_selfcheck(
    tasks: Sequence[Task],
    sandbox: SandboxConfig | None = None,
) -> SelfCheckReport:
    cfg = sandbox or SandboxConfig()
    report = SelfCheckReport(n_tasks=len(tasks))
    for task in tasks:
        problems = validate_fixture(task, cfg)
        if problems:
            report.fixture_problems[task.id] = problems
    if report.fixture_problems:
        return report

    budget = Budget()

    def oracle_factory(task: Task, _repeat: int) -> RepairAgent:
        return RepairAgent(oracle_client(task), budget=budget, sandbox=cfg)

    def null_factory(task: Task, _repeat: int) -> RepairAgent:
        return RepairAgent(null_client(), budget=budget, sandbox=cfg)

    def cheater_factory(task: Task, _repeat: int) -> RepairAgent:
        return RepairAgent(cheater_client(task), budget=budget, sandbox=cfg)

    oracle = run_eval(tasks, oracle_factory)
    report.oracle_resolved = oracle["aggregate"]["resolved"]
    null = run_eval(tasks, null_factory)
    report.null_resolved = null["aggregate"]["resolved"]
    cheater = run_eval(tasks, cheater_factory)
    report.cheater_blocked = sum(
        1
        for item in cheater["results"]
        if item["stop_reason"] == "policy_violations" and not item["resolved"]
    )
    report.cheater_tampered = cheater["aggregate"]["tamper_count"]
    return report
