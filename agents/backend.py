"""Swappable agent-runtime interface and OpenAI-compatible backend."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable, Sequence
from typing import Any, Literal, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

logger = logging.getLogger(__name__)

EffortLevel = Literal["low", "medium", "high"]


def translate_effort(
    effort: EffortLevel | str,
    provider: str,
) -> dict[str, Any]:
    """Translate effort level to provider-specific OpenAI-compatible reasoning parameters.

    Returns an empty dict if the provider is unsupported or does not support
    reasoning effort.
    """
    if effort not in ("low", "medium", "high"):
        return {}
    p = provider.lower().strip()
    if p in ("openai", "openrouter", "omniroute", "azure"):
        return {"reasoning_effort": str(effort)}
    return {}


class ToolCall(BaseModel):
    """A tool call requested by an LLM."""

    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolSpec(BaseModel):
    """Specification of an agent tool."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    input_model: type[BaseModel]
    fn: Callable[..., Any]

    def execute(self, tool_call: ToolCall) -> Any:
        """Validate input arguments against input_model and execute fn."""
        validated = self.input_model.model_validate(tool_call.args)
        if hasattr(validated, "model_dump"):
            dump = validated.model_dump()
            try:
                return self.fn(**dump)
            except TypeError:
                return self.fn(validated)
        return self.fn(**tool_call.args)


class AgentSpec(BaseModel):
    """Specification and runtime configuration of an agent."""

    name: str
    role: str
    model: str
    endpoint: str
    effort: EffortLevel = "medium"
    system_prompt: str = ""
    prompt_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.prompt_hash and self.system_prompt:
            self.prompt_hash = hashlib.sha256(self.system_prompt.encode("utf-8")).hexdigest()


class ChatMessage(BaseModel):
    """Single message in an agent's chat context."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


class OutgoingMessage(BaseModel):
    """Outgoing message to another agent or chat."""

    to_agent: str
    chat: str
    text: str


class Usage(BaseModel):
    """Token usage returned for accounting and registry only."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float | None = None


class StepResult(BaseModel):
    """Result of an agent step execution."""

    outgoing_messages: list[OutgoingMessage] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    content: str | None = None
    done: bool = True
    usage: Usage | None = None


@runtime_checkable
class AgentBackend(Protocol):
    """Swappable agent-runtime interface."""

    def step(
        self,
        agent: AgentSpec,
        chat_context: list[ChatMessage],
        tools: Sequence[ToolSpec],
    ) -> StepResult:
        """Execute a single reasoning step for an agent."""
        ...


class BackendError(Exception):
    """Base exception for backend communication errors."""


class NonTransientBackendError(BackendError):
    """Non-retryable backend error (e.g. 400, 401, 403)."""


class TransientBackendError(BackendError):
    """Retryable backend error (e.g. 429, 500, 503, connection timeouts)."""


class OpenAICompatibleBackend:
    """AgentBackend implementation calling OpenAI-compatible /chat/completions."""

    def __init__(
        self,
        api_key: str | SecretStr | None = None,
        provider: str = "openai",
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 2,
        initial_retry_wait: float = 0.5,
        backoff_factor: float = 2.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.provider = provider
        self.http_client = http_client
        self.transport = transport
        self.max_retries = max_retries
        self.initial_retry_wait = initial_retry_wait
        self.backoff_factor = backoff_factor
        self.sleep_fn = sleep_fn
        self.timeout = timeout

    def _resolve_api_key(self, agent: AgentSpec) -> str | None:
        if self.api_key is not None:
            if isinstance(self.api_key, SecretStr):
                return self.api_key.get_secret_value()
            return str(self.api_key)
        for env_var in ("OPENAI_API_KEY", "OMNIROUTE_API_KEY", "OPENROUTER_API_KEY"):
            val = os.environ.get(env_var)
            if val:
                return val
        return None

    def _format_messages(
        self, agent: AgentSpec, chat_context: list[ChatMessage]
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        has_system = any(m.role == "system" for m in chat_context)
        if agent.system_prompt and not has_system:
            messages.append({"role": "system", "content": agent.system_prompt})

        for msg in chat_context:
            item: dict[str, Any] = {"role": msg.role}
            if msg.content is not None:
                item["content"] = msg.content
            if msg.name is not None:
                item["name"] = msg.name
            if msg.tool_call_id is not None:
                item["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.args),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(item)

        return messages

    def _format_tools(self, tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_model.model_json_schema(),
                },
            }
            for t in tools
        ]

    def _build_url(self, endpoint: str) -> str:
        ep = endpoint.rstrip("/")
        if not ep.endswith("/chat/completions"):
            return f"{ep}/chat/completions"
        return ep

    def step(
        self,
        agent: AgentSpec,
        chat_context: list[ChatMessage],
        tools: Sequence[ToolSpec],
    ) -> StepResult:
        """Call /chat/completions with tool-calling and retry on transient errors."""
        url = self._build_url(agent.endpoint)
        messages_payload = self._format_messages(agent, chat_context)

        payload: dict[str, Any] = {
            "model": agent.model,
            "messages": messages_payload,
        }

        effort_params = translate_effort(agent.effort, self.provider)
        payload.update(effort_params)

        if tools:
            payload["tools"] = self._format_tools(tools)

        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._resolve_api_key(agent)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        client_created = False
        client = self.http_client
        if client is None:
            client = httpx.Client(transport=self.transport, timeout=self.timeout)
            client_created = True

        attempt = 0
        wait = self.initial_retry_wait

        try:
            while True:
                attempt += 1
                try:
                    # Sanitize log: never log Authorization headers or tokens
                    logger.debug(
                        "Calling agent %s model %s at %s (attempt %d/%d)",
                        agent.name,
                        agent.model,
                        url,
                        attempt,
                        self.max_retries + 1,
                    )

                    response = client.post(url, json=payload, headers=headers)

                    if response.is_success:
                        return self._parse_response(response.json())

                    status = response.status_code
                    if status in (429, 500, 502, 503, 504):
                        if attempt <= self.max_retries:
                            logger.warning(
                                "Transient HTTP %d from %s; retrying in %.2fs (attempt %d/%d)",
                                status,
                                url,
                                wait,
                                attempt,
                                self.max_retries + 1,
                            )
                            self.sleep_fn(wait)
                            wait *= self.backoff_factor
                            continue
                        raise TransientBackendError(
                            f"HTTP {status} after {attempt} attempts from {url}"
                        )

                    # Non-transient error (e.g. 400, 401, 403, 404): fail immediately
                    raise NonTransientBackendError(
                        f"Non-transient HTTP {status} from {url}: {response.text[:200]}"
                    )

                except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                    if attempt <= self.max_retries:
                        logger.warning(
                            "Transient network error calling %s; retrying in %.2fs (attempt %d/%d)",
                            url,
                            wait,
                            attempt,
                            self.max_retries + 1,
                        )
                        self.sleep_fn(wait)
                        wait *= self.backoff_factor
                        continue
                    raise TransientBackendError(
                        f"Network error after {attempt} attempts from {url}: {type(exc).__name__}"
                    ) from None
        finally:
            if client_created:
                client.close()

    def _parse_response(self, data: dict[str, Any]) -> StepResult:
        choices = data.get("choices", [])
        if not choices:
            raise BackendError("OpenAI-compatible endpoint returned empty choices")

        choice = choices[0]
        msg_data = choice.get("message", {})
        content = msg_data.get("content")

        tool_calls: list[ToolCall] = []
        outgoing_messages: list[OutgoingMessage] = []

        for tc_raw in msg_data.get("tool_calls") or []:
            func_data = tc_raw.get("function", {})
            name = func_data.get("name", "")
            args_raw = func_data.get("arguments", "{}")
            if isinstance(args_raw, str):
                try:
                    parsed_args = json.loads(args_raw)
                except json.JSONDecodeError:
                    parsed_args = {}
            elif isinstance(args_raw, dict):
                parsed_args = args_raw
            else:
                parsed_args = {}

            tc_obj = ToolCall(
                id=str(tc_raw.get("id", "")),
                name=name,
                args=parsed_args,
            )
            tool_calls.append(tc_obj)

            if name == "send_message" and isinstance(parsed_args, dict):
                if "to_agent" in parsed_args and "chat" in parsed_args and "text" in parsed_args:
                    outgoing_messages.append(
                        OutgoingMessage(
                            to_agent=str(parsed_args["to_agent"]),
                            chat=str(parsed_args["chat"]),
                            text=str(parsed_args["text"]),
                        )
                    )

        done = len(tool_calls) == 0

        usage = None
        raw_usage = data.get("usage")
        if raw_usage and isinstance(raw_usage, dict):
            usage = Usage(
                prompt_tokens=raw_usage.get("prompt_tokens", 0),
                completion_tokens=raw_usage.get("completion_tokens", 0),
                total_tokens=raw_usage.get("total_tokens", 0),
            )

        return StepResult(
            outgoing_messages=outgoing_messages,
            tool_calls=tool_calls,
            content=content,
            done=done,
            usage=usage,
        )
