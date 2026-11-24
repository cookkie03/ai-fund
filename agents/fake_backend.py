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
    ToolCall,
    ToolSpec,
    Usage,
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
        elif isinstance(self.script, (list, tuple)):
            if turn < len(self.script):
                result = self.script[turn]
            else:
                result = StepResult(content="OK", done=True)
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


class ScriptedBridgeBackend(AgentBackend):
    """Deterministic scripted backend for the Bridge Agent in development and tests."""

    def __init__(self, fallback: AgentBackend | None = None) -> None:
        self.fallback = fallback
        self.calls: list[RecordedCall] = []
        self._turn_counts: dict[str, int] = defaultdict(int)

    def step(
        self,
        agent: AgentSpec,
        chat_context: list[ChatMessage],
        tools: Sequence[ToolSpec],
    ) -> StepResult:
        if agent.name != "bridge":
            if self.fallback:
                return self.fallback.step(agent, chat_context, tools)
            return StepResult(content="OK", done=True)

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

        last_user_msg = next((m.content for m in reversed(chat_context) if m.role == "user"), "")
        lower = last_user_msg.lower()

        # Step 0: invoke tool
        has_tool_result = any(
            m.role == "system" and "Risultato tool" in m.content for m in chat_context
        )
        if not has_tool_result:
            if "chiudi" in lower or "vendi" in lower or "close" in lower:
                target_ticker = "NVDA"
                for sym in (
                    "AAPL",
                    "GOOGL",
                    "META",
                    "MSFT",
                    "AMD",
                    "JPM",
                    "XOM",
                    "LLY",
                    "TSLA",
                    "NVDA",
                ):
                    if sym.lower() in lower:
                        target_ticker = sym
                        break
                return StepResult(
                    tool_calls=[
                        ToolCall(
                            id="tc-close-1",
                            name="propose_action",
                            args={
                                "command": "close_position",
                                "payload": {"ticker": target_ticker, "qty": 5},
                                "summary": f"Chiudi 5 azioni {target_ticker} a mercato",
                            },
                        )
                    ],
                    done=False,
                    usage=Usage(prompt_tokens=200, completion_tokens=50, cost=0.01),
                )
            if "chiedi a" in lower or "messaggio a" in lower or "relay" in lower:
                return StepResult(
                    tool_calls=[
                        ToolCall(
                            id="tc-msg-1",
                            name="message_agent",
                            args={
                                "agent": "technical_analyst",
                                "topic": "AMD",
                                "text": "Puoi verificare i livelli tecnici?",
                            },
                        )
                    ],
                    done=False,
                    usage=Usage(prompt_tokens=200, completion_tokens=50, cost=0.01),
                )
            if "watchlist" in lower:
                return StepResult(
                    tool_calls=[
                        ToolCall(
                            id="tc-watch-1",
                            name="add_watchlist",
                            args={"ticker": "TSLA", "note": "Segnalato da Luca"},
                        )
                    ],
                    done=False,
                    usage=Usage(prompt_tokens=200, completion_tokens=50, cost=0.01),
                )
            # Default read tool
            return StepResult(
                tool_calls=[ToolCall(id="tc-read-1", name="read_portfolio", args={})],
                done=False,
                usage=Usage(prompt_tokens=200, completion_tokens=50, cost=0.01),
            )

        # Step 1: respond with content
        if "chiudi" in lower or "vendi" in lower or "close" in lower:
            target_ticker = "NVDA"
            for sym in (
                "AAPL",
                "GOOGL",
                "META",
                "MSFT",
                "AMD",
                "JPM",
                "XOM",
                "LLY",
                "TSLA",
                "NVDA",
            ):
                if sym.lower() in lower:
                    target_ticker = sym
                    break
            content = (
                f"Ho esaminato la posizione su {target_ticker} e ho preparato la proposta per chiudere 5 azioni a mercato. "
                "L'azione è registrata in attesa della tua conferma esplicita nella UI."
            )
        elif "chiedi a" in lower or "messaggio a" in lower or "relay" in lower:
            content = (
                "Ho inoltrato la richiesta a Technical Analyst per conto tuo sulla chat AMD. "
                "Non appena risponderà, la sintesi comparirà qui."
            )
        elif "watchlist" in lower:
            content = "Ho inserito TSLA nella watchlist dell'ufficio come richiesto."
        else:
            content = "Ho verificato la situazione del portafoglio e delle operazioni in corso. Tutto è allineato."

        return StepResult(
            content=content,
            done=True,
            usage=Usage(prompt_tokens=300, completion_tokens=80, cost=0.015),
        )
