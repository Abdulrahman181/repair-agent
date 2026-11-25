from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import httpx

from repairagent.config import LLMSettings
from repairagent.llm.base import LLMError, LLMResponse, LLMToolFormatError, ToolCall, Usage

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
BACKOFF_BASE_S = 1.0
BACKOFF_CAP_S = 30.0


class OpenAICompatClient:
    def __init__(
        self,
        settings: LLMSettings,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._http = http_client or httpx.Client(timeout=settings.timeout_s)
        self._sleep = sleep

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        settings = self._settings
        payload: dict[str, Any] = {
            "model": settings.model,
            "messages": messages,
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Content-Type": "application/json"}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        url = settings.base_url.rstrip("/") + "/chat/completions"

        last_error = "no attempt made"
        for attempt in range(settings.max_retries + 1):
            started = time.perf_counter()
            try:
                response = self._http.post(url, json=payload, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = type(exc).__name__
                self._backoff(attempt, None)
                continue
            latency = time.perf_counter() - started
            if response.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
                self._backoff(attempt, response.headers.get("retry-after"))
                continue
            if response.status_code == 400 and "tool_use_failed" in response.text:
                raise LLMToolFormatError("provider rejected a malformed tool call")
            if response.status_code >= 400:
                raise LLMError(f"HTTP {response.status_code}: {response.text[:300]}")
            return self._parse(response, latency)
        raise LLMError(f"retries exhausted ({last_error})")

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        if attempt >= self._settings.max_retries:
            return
        delay = min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2**attempt))
        if retry_after:
            try:
                delay = min(BACKOFF_CAP_S, max(0.0, float(retry_after)))
            except ValueError:
                pass
        self._sleep(delay)

    @staticmethod
    def _parse(response: httpx.Response, latency: float) -> LLMResponse:
        try:
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("unexpected response shape from provider") from exc
        raw_calls = message.get("tool_calls") or []
        calls = tuple(_parse_call(raw, index) for index, raw in enumerate(raw_calls))
        usage_data = data.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(usage_data.get("prompt_tokens") or 0),
            completion_tokens=int(usage_data.get("completion_tokens") or 0),
        )
        return LLMResponse(
            content=message.get("content"),
            tool_calls=calls,
            usage=usage,
            finish_reason=str(choice.get("finish_reason") or ""),
            latency_s=latency,
        )


def _parse_call(raw: dict[str, Any], index: int) -> ToolCall:
    function = raw.get("function") or {}
    name = str(function.get("name") or "")
    call_id = str(raw.get("id") or f"call_{index}")
    arguments = function.get("arguments")
    if isinstance(arguments, dict):
        return ToolCall(call_id, name, arguments, json.dumps(arguments))
    text = arguments if isinstance(arguments, str) and arguments.strip() else "{}"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return ToolCall(call_id, name, None, text, f"invalid JSON ({exc.msg})")
    if not isinstance(parsed, dict):
        return ToolCall(call_id, name, None, text, "arguments must be a JSON object")
    return ToolCall(call_id, name, parsed, text)
