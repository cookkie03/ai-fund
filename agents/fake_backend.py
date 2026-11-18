"""Deterministic fake backend for office engine tests."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from agents.backend import (
    AgentBackend,
    AgentSpec,
    ChatMessage,
    StepResult,
    ToolSpec,
)


@dataclass(frozen=True)
class RecordedCall:
    """Record of a single step invocation."""

    agent: AgentSpec
    chat_context: list[ChatMessage]
    tools: Sequence[ToolSpec]
    turn_index: int


ScriptType = (
    Mapping[tuple[str, int], StepResult | Exception]
    | Mapping[str, list[StepResult | Exception]]
    | Callable[..., StepResult | Exception]
)


class ScriptedBackend(AgentBackend):
    """Deterministic fake backend for engine testing.

    Accepts a script mapping (agent_name, turn_index) -> StepResult, or an
    agent_name -> list[StepResult] sequence, or a callable.
    Records every call received for assertions.
    """

    def __init__(self, script: ScriptType) -> None:
        self.script = script
        self.calls: list[RecordedCall] = []
        self._turn_counts: dict[str, int] = defaultdict(int)

    def step(
        self,
        agent: AgentSpec,
        chat_context: list[ChatMessage],
        tools: Sequence[ToolSpec],
    ) -> StepResult:
        turn = self._turn_counts[agent.name]
        self._turn_counts[agent.name] += 1

        self.calls.append(
            RecordedCall(
                agent=agent,
                chat_context=list(chat_context),
                tools=tools,
                turn_index=turn,
            )
        )

        result: StepResult | Exception
        if callable(self.script):
            try:
                result = self.script(agent, chat_context, tools, turn)
            except TypeError:
                result = self.script(agent, chat_context, tools)
        elif isinstance(self.script, Mapping):
            key = (agent.name, turn)
            if key in self.script:
                result = self.script[key]
            elif agent.name in self.script:
                agent_turns = self.script[agent.name]
                if isinstance(agent_turns, (list, tuple)) and turn < len(agent_turns):
                    result = agent_turns[turn]
                else:
                    raise KeyError(
                        f"ScriptedBackend: agent '{agent.name}' exceeded scripted turns "
                        f"(turn={turn})"
                    )
            else:
                raise KeyError(
                    f"ScriptedBackend: no scripted response for agent '{agent.name}' at turn {turn}"
                )
        else:
            raise TypeError(f"ScriptedBackend: unsupported script type {type(self.script)}")

        if isinstance(result, Exception):
            raise result

        return result

    def reset(self) -> None:
        """Clear recorded calls and reset turn counters."""
        self.calls.clear()
        self._turn_counts.clear()

    def calls_for_agent(self, agent_name: str) -> list[RecordedCall]:
        """Return calls recorded for a specific agent."""
        return [c for c in self.calls if c.agent.name == agent_name]
