from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from repairagent.llm.base import LLMError, LLMResponse, ToolCall, Usage

ScriptItem = LLMResponse | Exception | Callable[[list[dict[str, Any]]], LLMResponse]


def tool_call_response(
    name: str,
    arguments: dict[str, Any] | None = None,
    call_id: str = "call_0",
    usage: Usage | None = None,
) -> LLMResponse:
    args = arguments or {}
    call = ToolCall(call_id, name, args, json.dumps(args))
    return LLMResponse(None, (call,), usage or Usage(100, 20), "tool_calls")


def text_response(text: str, usage: Usage | None = None) -> LLMResponse:
    return LLMResponse(text, (), usage or Usage(100, 20), "stop")


class ScriptedClient:
    def __init__(self, script: list[ScriptItem]) -> None:
        self._script = list(script)
        self._cursor = 0
        self.calls: list[list[dict[str, Any]]] = []

    @property
    def exhausted(self) -> bool:
        return self._cursor >= len(self._script)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self.calls.append([dict(message) for message in messages])
        if self._cursor >= len(self._script):
            raise LLMError("scripted client exhausted")
        item = self._script[self._cursor]
        self._cursor += 1
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(messages)
        return item
