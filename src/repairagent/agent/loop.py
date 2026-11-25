from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from repairagent.agent.prompts import (
    FORMAT_NUDGE,
    NO_TOOL_NUDGE,
    REPEAT_NOTE,
    SYSTEM_PROMPT,
    build_task_message,
)
from repairagent.config import Budget
from repairagent.llm.base import LLMClient, LLMError, LLMToolFormatError
from repairagent.policy import Policy
from repairagent.sandbox.runner import SandboxConfig
from repairagent.sandbox.workspace import Workspace
from repairagent.store import RunStore
from repairagent.tasks import Task
from repairagent.tools.base import RunState, ToolContext, ToolRegistry
from repairagent.tools.builtin import build_registry
from repairagent.verify import Verdict, verify

MAX_CALLS_PER_TURN = 4
NO_TOOL_LIMIT = 3
MAX_TOOL_CHARS = 6000


@dataclass
class AgentRunResult:
    run_id: int | None
    task_id: str
    stop_reason: str
    steps: int
    prompt_tokens: int
    completion_tokens: int
    wall_s: float
    policy_violations: int
    files_changed: list[str]
    summary: str
    verdict: Verdict
    meta: dict[str, Any] = field(default_factory=dict)


def _clip(text: str, limit: int = MAX_TOOL_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


class RepairAgent:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry | None = None,
        policy: Policy | None = None,
        budget: Budget | None = None,
        sandbox: SandboxConfig | None = None,
        store: RunStore | None = None,
        run_meta: dict[str, Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.llm = llm
        self.registry = registry or build_registry()
        self.policy = policy or Policy()
        self.budget = budget or Budget()
        self.sandbox = sandbox or SandboxConfig()
        self.store = store
        self.run_meta = run_meta or {}
        self.clock = clock

    def run(self, task: Task) -> AgentRunResult:
        workspace = Workspace.from_template(task.repo_dir)
        try:
            return self._run(task, workspace)
        finally:
            workspace.cleanup()

    def _log(self, run_id: int | None, kind: str, **fields: Any) -> None:
        if self.store is not None and run_id is not None:
            self.store.add_step(run_id, kind, **fields)

    def _run(self, task: Task, workspace: Workspace) -> AgentRunResult:
        budget = self.budget
        baseline = workspace.hash_files(self.policy.is_protected)
        state = RunState()
        ctx = ToolContext(workspace, self.policy, self.sandbox, state, budget.max_test_runs)
        run_id = self.store.create_run(task.id, self.run_meta) if self.store else None
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_task_message(task)},
        ]
        specs = self.registry.specs()
        started = self.clock()

        prompt_tokens = 0
        completion_tokens = 0
        steps = 0
        violations = 0
        no_tool_turns = 0
        summary = ""
        stop_reason = "max_steps"
        seen: dict[str, int] = {}

        while True:
            if steps >= budget.max_steps:
                stop_reason = "max_steps"
                break
            if prompt_tokens + completion_tokens >= budget.max_total_tokens:
                stop_reason = "max_tokens"
                break
            if self.clock() - started >= budget.max_wall_s:
                stop_reason = "timeout"
                break
            steps += 1

            try:
                response = self.llm.chat(messages, specs)
            except LLMToolFormatError as exc:
                self._log(run_id, "llm_error", result=str(exc), ok=False)
                no_tool_turns += 1
                if no_tool_turns >= NO_TOOL_LIMIT:
                    stop_reason = "no_tool_calls"
                    break
                messages.append({"role": "user", "content": FORMAT_NUDGE})
                continue
            except LLMError as exc:
                self._log(run_id, "llm_error", result=str(exc), ok=False)
                stop_reason = "llm_error"
                break

            prompt_tokens += response.usage.prompt_tokens
            completion_tokens += response.usage.completion_tokens
            self._log(
                run_id,
                "llm",
                result=response.content,
                latency_s=response.latency_s,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )

            calls = response.tool_calls[:MAX_CALLS_PER_TURN]
            if not calls:
                messages.append({"role": "assistant", "content": response.content or ""})
                no_tool_turns += 1
                if no_tool_turns >= NO_TOOL_LIMIT:
                    stop_reason = "no_tool_calls"
                    break
                messages.append({"role": "user", "content": NO_TOOL_NUDGE})
                continue
            no_tool_turns = 0

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.raw_arguments or "{}",
                            },
                        }
                        for call in calls
                    ],
                }
            )

            finished = False
            stalled = False
            for call in calls:
                key = (
                    f"{call.name}:{json.dumps(call.arguments, sort_keys=True, default=str)}"
                    f":{state.edit_version}"
                )
                seen[key] = seen.get(key, 0) + 1
                tool_started = time.perf_counter()
                result = self.registry.execute(call, ctx)
                text = result.text
                if seen[key] == budget.max_repeat_actions - 1:
                    text += REPEAT_NOTE
                if seen[key] >= budget.max_repeat_actions:
                    stalled = True
                if result.policy_violation:
                    violations += 1
                self._log(
                    run_id,
                    "tool",
                    tool=call.name,
                    args=call.arguments,
                    result=text,
                    ok=result.ok,
                    policy_violation=result.policy_violation,
                    latency_s=time.perf_counter() - tool_started,
                )
                messages.append({"role": "tool", "tool_call_id": call.id, "content": _clip(text)})
                if result.terminal:
                    finished = True
                    summary = str(result.data.get("summary", ""))
                    break

            if finished:
                stop_reason = "finished"
                break
            if violations >= budget.max_policy_violations:
                stop_reason = "policy_violations"
                break
            if stalled:
                stop_reason = "stalled"
                break

        wall_s = self.clock() - started
        verdict = verify(task, workspace, baseline, self.policy, self.sandbox)
        result_obj = AgentRunResult(
            run_id=run_id,
            task_id=task.id,
            stop_reason=stop_reason,
            steps=steps,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            wall_s=wall_s,
            policy_violations=violations,
            files_changed=sorted(state.files_changed),
            summary=summary,
            verdict=verdict,
            meta=dict(self.run_meta),
        )
        if self.store is not None and run_id is not None:
            self.store.finish_run(
                run_id,
                stop_reason=stop_reason,
                resolved=verdict.resolved,
                visible_pass=verdict.visible_pass,
                hidden_pass=verdict.hidden_pass,
                tampered=verdict.tampered,
                steps=steps,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                policy_violations=violations,
                wall_s=wall_s,
                summary=summary,
            )
        return result_obj
