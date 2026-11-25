from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from repairagent.config import ConfigError, LLMSettings, load_env_file
from repairagent.llm import LLMError, LLMToolFormatError, OpenAICompatClient

SECRET = "gsk_test_secret_key_123"


def settings(**overrides) -> LLMSettings:
    base = {
        "provider": "groq",
        "model": "test-model",
        "base_url": "https://llm.example/v1",
        "api_key": SECRET,
        "max_retries": 3,
    }
    base.update(overrides)
    return LLMSettings(**base)


def make_client(handler, **overrides):
    sleeps: list[float] = []
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAICompatClient(settings(**overrides), http_client=http, sleep=sleeps.append)
    return client, sleeps


def ok_body(message: dict, usage: dict | None = None) -> dict:
    return {
        "choices": [{"message": message, "finish_reason": "tool_calls"}],
        "usage": usage or {"prompt_tokens": 11, "completion_tokens": 7},
    }


TOOL_MESSAGE = {
    "content": None,
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "read_file", "arguments": '{"path": "pager.py"}'},
        }
    ],
}


def test_parses_tool_calls_and_usage():
    client, _ = make_client(lambda request: httpx.Response(200, json=ok_body(TOOL_MESSAGE)))
    response = client.chat([{"role": "user", "content": "hi"}], [])
    assert response.content is None
    call = response.tool_calls[0]
    assert (call.id, call.name, call.arguments) == ("call_1", "read_file", {"path": "pager.py"})
    assert call.parse_error is None
    assert response.usage.prompt_tokens == 11
    assert response.usage.completion_tokens == 7
    assert response.usage.total == 18
    assert response.finish_reason == "tool_calls"


def test_request_shape_and_auth_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body({"content": "hello"}))

    client, _ = make_client(handler)
    tools = [{"type": "function", "function": {"name": "t", "parameters": {"type": "object"}}}]
    client.chat([{"role": "user", "content": "x"}], tools)
    assert seen["url"] == "https://llm.example/v1/chat/completions"
    assert seen["auth"] == f"Bearer {SECRET}"
    assert seen["body"]["model"] == "test-model"
    assert seen["body"]["tools"] == tools
    assert seen["body"]["tool_choice"] == "auto"
    assert seen["body"]["temperature"] == 0.0


def test_no_tools_means_no_tool_choice():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body({"content": "hello"}))

    client, _ = make_client(handler)
    client.chat([{"role": "user", "content": "x"}], [])
    assert "tools" not in seen["body"] and "tool_choice" not in seen["body"]


def test_no_auth_header_without_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=ok_body({"content": "hello"}))

    client, _ = make_client(handler, api_key=None)
    client.chat([], [])
    assert seen["auth"] is None


def test_arguments_given_as_dict():
    message = {
        "content": "",
        "tool_calls": [{"function": {"name": "finish", "arguments": {"summary": "ok"}}}],
    }
    client, _ = make_client(lambda request: httpx.Response(200, json=ok_body(message)))
    call = client.chat([], []).tool_calls[0]
    assert call.arguments == {"summary": "ok"}
    assert call.id == "call_0"


def test_invalid_json_arguments_are_flagged_not_raised():
    message = {"content": None, "tool_calls": [{"function": {"name": "x", "arguments": "{oops"}}]}
    client, _ = make_client(lambda request: httpx.Response(200, json=ok_body(message)))
    call = client.chat([], []).tool_calls[0]
    assert call.arguments is None
    assert "invalid JSON" in (call.parse_error or "")
    assert call.raw_arguments == "{oops"


def test_non_object_arguments_are_flagged():
    message = {"content": None, "tool_calls": [{"function": {"name": "x", "arguments": "[1, 2]"}}]}
    client, _ = make_client(lambda request: httpx.Response(200, json=ok_body(message)))
    call = client.chat([], []).tool_calls[0]
    assert call.parse_error == "arguments must be a JSON object"


def test_empty_arguments_become_empty_object():
    message = {
        "content": None,
        "tool_calls": [{"function": {"name": "list_files", "arguments": ""}}],
    }
    client, _ = make_client(lambda request: httpx.Response(200, json=ok_body(message)))
    call = client.chat([], []).tool_calls[0]
    assert call.arguments == {} and call.parse_error is None


def test_retries_rate_limit_and_honours_retry_after():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429, headers={"retry-after": "2"}, text="slow down")
        return httpx.Response(200, json=ok_body({"content": "finally"}))

    client, sleeps = make_client(handler)
    assert client.chat([], []).content == "finally"
    assert len(attempts) == 3
    assert sleeps == [2.0, 2.0]


def test_exponential_backoff_without_retry_after():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 4:
            return httpx.Response(503)
        return httpx.Response(200, json=ok_body({"content": "up"}))

    client, sleeps = make_client(handler)
    client.chat([], [])
    assert sleeps == [1.0, 2.0, 4.0]


def test_retry_after_is_capped():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "9999"})
        return httpx.Response(200, json=ok_body({"content": "ok"}))

    client, sleeps = make_client(handler)
    client.chat([], [])
    assert sleeps == [30.0]


def test_retries_exhausted_raises():
    client, sleeps = make_client(lambda request: httpx.Response(500))
    with pytest.raises(LLMError, match="retries exhausted"):
        client.chat([], [])
    assert len(sleeps) == 3


def test_transport_errors_are_retried():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json=ok_body({"content": "recovered"}))

    client, _ = make_client(handler)
    assert client.chat([], []).content == "recovered"


def test_tool_use_failed_maps_to_format_error():
    body = {"error": {"code": "tool_use_failed", "message": "bad generation"}}
    client, _ = make_client(lambda request: httpx.Response(400, json=body))
    with pytest.raises(LLMToolFormatError):
        client.chat([], [])


def test_client_errors_are_not_retried_and_do_not_leak_key():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    client, sleeps = make_client(handler)
    with pytest.raises(LLMError) as info:
        client.chat([], [])
    assert len(calls) == 1 and sleeps == []
    assert "401" in str(info.value)
    assert SECRET not in str(info.value)


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{}]}])
def test_unexpected_response_shape(body):
    client, _ = make_client(lambda request: httpx.Response(200, json=body))
    with pytest.raises(LLMError, match="unexpected response"):
        client.chat([], [])


def test_non_json_success_body():
    client, _ = make_client(lambda request: httpx.Response(200, text="<html>"))
    with pytest.raises(LLMError, match="unexpected response"):
        client.chat([], [])


def test_missing_usage_defaults_to_zero():
    body = {"choices": [{"message": {"content": "x"}}]}
    client, _ = make_client(lambda request: httpx.Response(200, json=body))
    assert client.chat([], []).usage.total == 0


def test_settings_requires_model():
    with pytest.raises(ConfigError, match="LLM_MODEL"):
        LLMSettings.from_env(environ={"GROQ_API_KEY": "k"})


def test_settings_requires_key_for_groq():
    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        LLMSettings.from_env(model="m", environ={})


def test_settings_unknown_provider():
    with pytest.raises(ConfigError, match="Unknown provider"):
        LLMSettings.from_env(provider="nope", model="m", environ={})


def test_settings_ollama_needs_no_key():
    loaded = LLMSettings.from_env(provider="ollama", model="qwen2.5:3b", environ={})
    assert loaded.api_key is None
    assert loaded.base_url == "http://localhost:11434/v1"


def test_settings_env_overrides():
    env = {
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": "m",
        "OPENAI_API_KEY": "k1",
        "LLM_API_KEY": "k2",
        "LLM_BASE_URL": "https://proxy.example/v1",
        "LLM_TEMPERATURE": "0.3",
        "LLM_MAX_RETRIES": "1",
    }
    loaded = LLMSettings.from_env(environ=env)
    assert loaded.api_key == "k2"
    assert loaded.base_url == "https://proxy.example/v1"
    assert loaded.temperature == 0.3 and loaded.max_retries == 1


def test_load_env_file_does_not_override(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\nLLM_MODEL=from-file\nGROQ_API_KEY='quoted'\n\nbroken line\nEXISTING=new\n",
        encoding="utf-8",
    )
    target = {"EXISTING": "old"}
    assert load_env_file(path, target) == 2
    assert target == {"EXISTING": "old", "LLM_MODEL": "from-file", "GROQ_API_KEY": "quoted"}


def test_load_env_file_missing(tmp_path: Path):
    assert load_env_file(tmp_path / "none.env", {}) == 0
