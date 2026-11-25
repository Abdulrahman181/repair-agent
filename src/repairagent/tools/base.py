from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from repairagent.llm.base import ToolCall
from repairagent.policy import Policy, PolicyViolation
from repairagent.sandbox.runner import PytestSummary, SandboxConfig
from repairagent.sandbox.workspace import PathEscape, Workspace


class ToolError(Exception):
    pass


@dataclass
class ToolResult:
    ok: bool
    text: str
    policy_violation: bool = False
    terminal: bool = False
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunState:
    edits: int = 0
    edit_version: int = 0
    test_runs: int = 0
    files_changed: set[str] = field(default_factory=set)
    last_tests: PytestSummary | None = None


@dataclass
class ToolContext:
    workspace: Workspace
    policy: Policy
    sandbox: SandboxConfig
    state: RunState
    max_test_runs: int = 8


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[ToolContext, Any], ToolResult]

    def spec(self) -> dict[str, Any]:
        schema = _strip_titles(self.args_model.model_json_schema())
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }


def _strip_titles(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: _strip_titles(value)
            for key, value in node.items()
            if not (key == "title" and isinstance(value, str))
        }
    if isinstance(node, list):
        return [_strip_titles(item) for item in node]
    return node


def _format_validation(error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "arguments"
        parts.append(f"{location}: {item['msg']}")
    return "; ".join(parts)


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        return [tool.spec() for tool in self._tools.values()]

    def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                False, f"Unknown tool '{call.name}'. Available tools: {', '.join(self._tools)}."
            )
        if call.parse_error:
            return ToolResult(False, f"Could not parse tool arguments: {call.parse_error}.")
        try:
            args = tool.args_model.model_validate(call.arguments or {})
        except ValidationError as exc:
            return ToolResult(False, f"Invalid arguments: {_format_validation(exc)}")
        try:
            return tool.handler(ctx, args)
        except (PolicyViolation, PathEscape) as exc:
            return ToolResult(False, f"Policy violation: {exc}", policy_violation=True)
        except ToolError as exc:
            return ToolResult(False, str(exc))
        except Exception as exc:
            return ToolResult(False, f"Internal tool error: {type(exc).__name__}")
