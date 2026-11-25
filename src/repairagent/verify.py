from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from repairagent.policy import Policy
from repairagent.sandbox.runner import PytestSummary, SandboxConfig, run_pytest
from repairagent.sandbox.workspace import Workspace
from repairagent.tasks import Task

HIDDEN_DIRNAME = "_hidden_tests"


@dataclass
class Verdict:
    resolved: bool
    visible_pass: bool
    hidden_pass: bool
    tampered: bool
    tampered_files: list[str] = field(default_factory=list)
    visible: PytestSummary = field(default_factory=PytestSummary)
    hidden: PytestSummary = field(default_factory=PytestSummary)


def install_hidden_tests(workspace: Workspace, task: Task) -> None:
    target = workspace.root / HIDDEN_DIRNAME
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(task.hidden_dir, target)


def overlay_reference(workspace: Workspace, task: Task) -> None:
    for rel in task.reference_files():
        destination = workspace.root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(task.reference_dir / rel, destination)


def _shadowing_files(workspace: Workspace, task: Task, policy: Policy) -> list[str]:
    with Workspace(task.repo_dir) as pristine:
        original = set(pristine.iter_files())
    return sorted(
        rel
        for rel in workspace.iter_files()
        if rel not in original and policy.shadowed_module(rel) is not None
    )


def _restore_protected(clone: Workspace, task: Task, policy: Policy) -> None:
    for rel in _shadowing_files(clone, task, policy):
        (clone.root / rel).unlink()
    for rel in list(clone.iter_files()):
        if policy.is_protected(rel):
            (clone.root / rel).unlink()
    with Workspace(task.repo_dir) as pristine:
        for rel in pristine.iter_files():
            if policy.is_protected(rel):
                destination = clone.root / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(pristine.root / rel, destination)


def verify(
    task: Task,
    workspace: Workspace,
    baseline_hashes: dict[str, str],
    policy: Policy,
    sandbox: SandboxConfig,
) -> Verdict:
    current = workspace.hash_files(policy.is_protected)
    changed = {
        path
        for path in set(baseline_hashes) | set(current)
        if baseline_hashes.get(path) != current.get(path)
    }
    tampered_files = sorted(changed | set(_shadowing_files(workspace, task, policy)))
    clone = workspace.clone()
    try:
        _restore_protected(clone, task, policy)
        _, visible = run_pytest(clone.root, (), sandbox)
        install_hidden_tests(clone, task)
        _, hidden = run_pytest(clone.root, (HIDDEN_DIRNAME,), sandbox)
    finally:
        clone.cleanup()
    tampered = bool(tampered_files)
    return Verdict(
        resolved=visible.ok and hidden.ok and not tampered,
        visible_pass=visible.ok,
        hidden_pass=hidden.ok,
        tampered=tampered,
        tampered_files=tampered_files,
        visible=visible,
        hidden=hidden,
    )
