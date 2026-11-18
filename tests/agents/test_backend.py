"""Tests for the agent runtime backend interface and implementations."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, Field, ValidationError

from agents.backend import (
    AgentBackend,
    AgentSpec,
    ChatMessage,
    NonTransientBackendError,
    OpenAICompatibleBackend,
    OutgoingMessage,
    StepResult,
    ToolCall,
    ToolSpec,
    TransientBackendError,
    Usage,
    translate_effort,
)
from agents.fake_backend import ScriptedBackend


class DummyArgs(BaseModel):
    query: str
    limit: int = Field(default=5)


class SendMessageArgs(BaseModel):
    to_agent: str
    chat: str
    text: str


# -----------------------------------------------------------------------------
# 1. translate_effort tests
# -----------------------------------------------------------------------------


def test_translate_effort_supported_providers() -> None:
    for provider in ("openai", "openrouter", "omniroute", "azure", "OpenAI", "OmniRoute "):
        for effort in ("low", "medium", "high"):
            params = translate_effort(effort, provider)
            assert params == {"reasoning_effort": effort}


def test_translate_effort_unsupported_or_invalid() -> None:
    assert translate_effort("medium", "ollama") == {}
    assert translate_effort("high", "groq") == {}
    assert translate_effort("low", "anthropic") == {}
    assert translate_effort("extreme", "openai") == {}
    assert translate_effort("", "omniroute") == {}


# -----------------------------------------------------------------------------
# 2. AgentSpec tests
# -----------------------------------------------------------------------------


def test_agent_spec_prompt_hash_auto_generation() -> None:
    agent = AgentSpec(
        name="risk_analyst",
        role="Risk Analyst",
        model="my-combo",
        endpoint="http://localhost:8000/v1",
        effort="medium",
        system_prompt="You are the Risk Analyst.",
    )
    assert agent.prompt_hash != ""
    assert len(agent.prompt_hash) == 64  # sha256 hex string


def test_agent_spec_explicit_prompt_hash_preserved() -> None:
    agent = AgentSpec(
        name="pm",
        role="Portfolio Manager",
        model="my-combo",
        endpoint="http://localhost:8000/v1",
        system_prompt="Prompt text",
        prompt_hash="custom_hash_123",
    )
    assert agent.prompt_hash == "custom_hash_123"


# -----------------------------------------------------------------------------
# 3. ToolSpec & ToolCall tests
# -----------------------------------------------------------------------------


def test_tool_spec_execution() -> None:
    executed_with: dict[str, Any] = {}

    def dummy_fn(query: str, limit: int = 5) -> str:
        executed_with["query"] = query
        executed_with["limit"] = limit
        return f"result: {query} (limit={limit})"

    tool = ToolSpec(
        name="search",
        description="Search news",
        input_model=DummyArgs,
        fn=dummy_fn,
    )

    tc = ToolCall(id="call_1", name="search", args={"query": "AAPL earnings", "limit": 10})
    result = tool.execute(tc)

    assert result == "result: AAPL earnings (limit=10)"
    assert executed_with == {"query": "AAPL earnings", "limit": 10}


def test_tool_spec_validation_error() -> None:
    tool = ToolSpec(
        name="search",
        description="Search news",
        input_model=DummyArgs,
        fn=lambda query, limit=5: query,
    )
    # Missing required query field
    tc = ToolCall(id="call_1", name="search", args={"limit": 10})
    with pytest.raises(ValidationError):
        tool.execute(tc)


# -----------------------------------------------------------------------------
# 4. ScriptedBackend tests
# -----------------------------------------------------------------------------


def test_scripted_backend_mapping_and_recording() -> None:
    agent = AgentSpec(
        name="pm",
        role="Portfolio Manager",
        model="test-model",
        endpoint="http://fake",
    )
    res_0 = StepResult(
        tool_calls=[ToolCall(id="1", name="search", args={"query": "test"})],
        done=False,
    )
    res_1 = StepResult(
        content="Final decision: accept",
        done=True,
    )

    script = {
        ("pm", 0): res_0,
        ("pm", 1): res_1,
    }
    backend = ScriptedBackend(script)
    assert isinstance(backend, AgentBackend)

    chat = [ChatMessage(role="user", content="Analyze ticker AAPL")]
    step_0 = backend.step(agent, chat, [])
    assert step_0 == res_0
    assert not step_0.done

    chat.append(ChatMessage(role="assistant", tool_calls=step_0.tool_calls))
    chat.append(ChatMessage(role="tool", tool_call_id="1", content="results"))

    step_1 = backend.step(agent, chat, [])
    assert step_1 == res_1
    assert step_1.done

    # Assert recorded calls
    assert len(backend.calls) == 2
    assert backend.calls[0].turn_index == 0
    assert backend.calls[1].turn_index == 1
    assert backend.calls[0].agent.name == "pm"
    assert len(backend.calls_for_agent("pm")) == 2
    assert len(backend.calls_for_agent("other")) == 0

    backend.reset()
    assert len(backend.calls) == 0


def test_scripted_backend_callable_and_exceptions() -> None:
    agent = AgentSpec(name="analyst", role="Analyst", model="test", endpoint="http://fake")

    def dynamic_script(ag: AgentSpec, ctx: list[ChatMessage], tools: Any, turn: int) -> StepResult:
        if turn == 0:
            return StepResult(content=f"Hello turn {turn}", done=True)
        raise RuntimeError("Forced engine crash")

    backend = ScriptedBackend(dynamic_script)
    res = backend.step(agent, [], [])
    assert res.content == "Hello turn 0"

    with pytest.raises(RuntimeError, match="Forced engine crash"):
        backend.step(agent, [], [])


def test_scripted_backend_missing_turn_raises_key_error() -> None:
    agent = AgentSpec(name="pm", role="PM", model="m", endpoint="e")
    backend = ScriptedBackend({})
    with pytest.raises(KeyError, match="pm"):
        backend.step(agent, [], [])


# -----------------------------------------------------------------------------
# 5. OpenAICompatibleBackend unit tests with MockTransport
# -----------------------------------------------------------------------------


def test_openai_compatible_backend_text_response() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "my-combo"
        assert body["reasoning_effort"] == "high"

        response_data = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Analysis completed. Accept order.",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 40,
                "total_tokens": 190,
            },
        }
        return httpx.Response(200, json=response_data)

    transport = httpx.MockTransport(handler)
    backend = OpenAICompatibleBackend(
        api_key="secret-key-12345",
        provider="openai",
        transport=transport,
    )

    agent = AgentSpec(
        name="pm",
        role="Portfolio Manager",
        model="my-combo",
        endpoint="https://api.openai.com/v1",
        effort="high",
        system_prompt="You are PM.",
    )
    chat = [ChatMessage(role="user", content="Start cycle for AAPL")]

    result = backend.step(agent, chat, [])

    assert result.done is True
    assert result.content == "Analysis completed. Accept order."
    assert len(result.tool_calls) == 0
    assert result.usage == Usage(prompt_tokens=150, completion_tokens=40, total_tokens=190)

    # Request header checks
    req = captured_requests[0]
    assert req.headers["Authorization"] == "Bearer secret-key-12345"
    assert req.url == "https://api.openai.com/v1/chat/completions"


def test_openai_compatible_backend_tool_calls_and_outgoing_messages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response_data = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_msg_1",
                                "type": "function",
                                "function": {
                                    "name": "send_message",
                                    "arguments": json.dumps(
                                        {
                                            "to_agent": "technical_analyst",
                                            "chat": "AAPL",
                                            "text": "What is the ATR and trend?",
                                        }
                                    ),
                                },
                            },
                            {
                                "id": "call_search_1",
                                "type": "function",
                                "function": {
                                    "name": "search_news",
                                    "arguments": json.dumps({"query": "AAPL"}),
                                },
                            },
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        }
        return httpx.Response(200, json=response_data)

    transport = httpx.MockTransport(handler)
    backend = OpenAICompatibleBackend(api_key="key", transport=transport)

    agent = AgentSpec(name="pm", role="PM", model="m", endpoint="http://local/v1")
    tool = ToolSpec(
        name="send_message",
        description="Send message",
        input_model=SendMessageArgs,
        fn=lambda **kw: "sent",
    )

    result = backend.step(agent, [ChatMessage(role="user", content="Analyze")], [tool])

    assert result.done is False
    assert len(result.tool_calls) == 2
    assert result.tool_calls[0].name == "send_message"
    assert result.tool_calls[1].name == "search_news"

    # Verify outgoing message was parsed from send_message tool call
    assert len(result.outgoing_messages) == 1
    out = result.outgoing_messages[0]
    assert isinstance(out, OutgoingMessage)
    assert out.to_agent == "technical_analyst"
    assert out.chat == "AAPL"
    assert out.text == "What is the ATR and trend?"


def test_openai_compatible_backend_retries_transient_http_errors() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            # 429 then 503 transient errors
            status = 429 if attempts == 1 else 503
            return httpx.Response(status, json={"error": "Rate limit / overloaded"})
        # 3rd attempt succeeds
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Recovered"}}],
            },
        )

    transport = httpx.MockTransport(handler)
    backend = OpenAICompatibleBackend(
        api_key="key",
        transport=transport,
        max_retries=2,
        initial_retry_wait=0.25,
        backoff_factor=2.0,
        sleep_fn=sleeps.append,
    )

    agent = AgentSpec(name="risk", role="Risk", model="m", endpoint="http://local/v1")
    res = backend.step(agent, [], [])

    assert res.content == "Recovered"
    assert attempts == 3
    # 2 retries means 2 sleep calls with backoff: 0.25, then 0.5
    assert sleeps == [0.25, 0.5]


def test_openai_compatible_backend_exhausted_retries_raises_transient() -> None:
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Persistent internal error"})

    transport = httpx.MockTransport(handler)
    backend = OpenAICompatibleBackend(
        api_key="key",
        transport=transport,
        max_retries=2,
        initial_retry_wait=0.1,
        sleep_fn=sleeps.append,
    )

    agent = AgentSpec(name="pm", role="PM", model="m", endpoint="http://local/v1")
    with pytest.raises(TransientBackendError, match="HTTP 500 after 3 attempts"):
        backend.step(agent, [], [])

    assert len(sleeps) == 2


def test_openai_compatible_backend_non_transient_error_no_retry() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, json={"error": "Invalid API key"})

    transport = httpx.MockTransport(handler)
    backend = OpenAICompatibleBackend(
        api_key="secret-bad-key",
        transport=transport,
        max_retries=2,
        sleep_fn=sleeps.append,
    )

    agent = AgentSpec(name="pm", role="PM", model="m", endpoint="http://local/v1")
    with pytest.raises(NonTransientBackendError) as exc_info:
        backend.step(agent, [], [])

    assert attempts == 1
    assert len(sleeps) == 0  # no retry for 401
    # Ensure secret is not in exception message
    assert "secret-bad-key" not in str(exc_info.value)


def test_openai_compatible_backend_no_secrets_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    transport = httpx.MockTransport(handler)
    secret_key = "[REDACTED:openai_compatible]"
    backend = OpenAICompatibleBackend(api_key=secret_key, transport=transport)

    agent = AgentSpec(name="pm", role="PM", model="m", endpoint="http://local/v1")
    backend.step(agent, [], [])

    for record in caplog.records:
        assert secret_key not in record.message
        assert "Authorization" not in record.message
