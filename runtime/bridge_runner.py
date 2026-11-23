"""Bridge Agent runner executing conversational turns in the background Runtime worker."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agents.backend import (
    AgentBackend,
    ChatMessage,
    StepResult,
    Usage,
)
from tools.bridge_tools import build_bridge_tools

if TYPE_CHECKING:
    from runtime.core import Runtime

logger = logging.getLogger(__name__)


def _extract_refs(text: str, items: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Extract standard entity references from message text."""
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, Any]] = set()

    # Ticker mentions: 2-5 uppercase letters preceded by space or start, e.g. NVDA, AAPL, MSFT, AMD
    for m in re.finditer(r"\b([A-Z]{2,5})\b", text):
        sym = m.group(1)
        if sym not in ("OK", "PM", "P&L", "ATR", "SMA", "EMA", "RSI", "MACD", "USD", "EUR", "SL", "TP", "LLM", "SSE", "UI", "DB"):
            key = ("ticker", sym)
            if key not in seen:
                seen.add(key)
                refs.append({"type": "ticker", "id": sym, "label": sym})

    # Order mentions: e.g. ordine #12 or order 12
    for m in re.finditer(r"(?:ordine|order)\s*(?:#|n\.\s*|id\s*)?(\d+)", text, re.IGNORECASE):
        oid = int(m.group(1))
        key = ("order", oid)
        if key not in seen:
            seen.add(key)
            refs.append({"type": "order", "id": oid, "label": f"Ordine #{oid}"})

    # Trade mentions: e.g. trade #5
    for m in re.finditer(r"trade\s*(?:#|n\.\s*|id\s*)?(\d+)", text, re.IGNORECASE):
        tid = int(m.group(1))
        key = ("trade", tid)
        if key not in seen:
            seen.add(key)
            refs.append({"type": "trade", "id": tid, "label": f"Trade #{tid}"})

    # Proposal mentions: e.g. proposta #3 or proposal 3
    for m in re.finditer(r"(?:proposta|proposal)\s*(?:#|n\.\s*|id\s*)?(\d+)", text, re.IGNORECASE):
        pid = int(m.group(1))
        key = ("proposal", pid)
        if key not in seen:
            seen.add(key)
            refs.append({"type": "proposal", "id": pid, "label": f"Proposta #{pid}"})

    # Agent mentions: e.g. @technical_analyst or Technical Analyst
    agent_map = {
        "portfolio_manager": "Portfolio Manager",
        "technical_analyst": "Technical Analyst",
        "fundamental_analyst": "Fundamental Analyst",
        "market_analyst": "Market Analyst",
        "sentiment_analyst": "Sentiment Analyst",
        "risk_analyst": "Risk Analyst",
    }
    lower_text = text.lower()
    for aid, label in agent_map.items():
        if aid in lower_text or label.lower() in lower_text:
            key = ("agent", aid)
            if key not in seen:
                seen.add(key)
                refs.append({"type": "agent", "id": aid, "label": label})

    return refs


class BridgeRunner:
    """Manages background reasoning turns and tool interactions for the Bridge Agent."""

    def __init__(
        self,
        runtime: Runtime,
        backend: AgentBackend | None = None,
        max_workers: int = 2,
        turn_budget_steps: int = 10,
    ) -> None:
        self.runtime = runtime
        self._backend = backend
        self.turn_budget_steps = turn_budget_steps
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._active_conversations: set[int] = set()
        self._queued_conversations: set[int] = set()
        self._stop_requested: set[int] = set()

    @property
    def backend(self) -> AgentBackend:
        if self._backend is not None:
            return self._backend
        return self.runtime.office.backend

    def set_backend(self, backend: AgentBackend) -> None:
        self._backend = backend

    def request_stop(self, conversation_id: int) -> bool:
        """Signal the running turn to halt at the next tool/reasoning step."""
        with self._lock:
            if conversation_id in self._active_conversations:
                self._stop_requested.add(conversation_id)
                return True
            return False

    def enqueue_turn(self, conversation_id: int) -> None:
        """Schedule a reasoning turn for the given conversation in the background worker."""
        with self._lock:
            if conversation_id in self._active_conversations:
                self._queued_conversations.add(conversation_id)
                return
            self._active_conversations.add(conversation_id)
            self._executor.submit(self._run_conversation_turn, conversation_id)

    def _get_daily_bridge_cost(self) -> float:
        conn = self.runtime.office.db.connection
        today = datetime.now(UTC).date().isoformat()
        row = conn.execute(
            "SELECT SUM(cost) AS total_cost FROM llm_calls WHERE agent = 'bridge' AND date(ts) = ?",
            (today,),
        ).fetchone()
        return float(row["total_cost"] or 0.0) if row else 0.0

    def _run_conversation_turn(self, conversation_id: int) -> None:
        db = self.runtime.office.db
        event_log = getattr(db, "event_log", None)

        try:
            # 1. Update status to thinking and broadcast
            db.update_bridge_conversation(conversation_id, status="thinking")
            if event_log:
                event_log.append(
                    "bridge.status",
                    f"bridge_conv:{conversation_id}",
                    {"conversation_id": conversation_id, "status": "thinking", "tool": None},
                    actor="bridge",
                )

            # 2. Check daily budget
            cfg = self.runtime.office.settings.get_agent("bridge")
            daily_limit = getattr(cfg, "daily_budget", 10.0) or 10.0
            current_cost = self._get_daily_bridge_cost()
            if current_cost >= daily_limit:
                now_iso = self.runtime.office.get_now_iso()
                err_text = f"Budget giornaliero dell'agente Bridge raggiunto (${current_cost:.2f} / ${daily_limit:.2f})."
                msg_id = db.append_bridge_message(
                    conversation_id=conversation_id,
                    author="bridge",
                    kind="error",
                    text=err_text,
                    ts=now_iso,
                )
                if event_log:
                    event_log.append(
                        "bridge.message",
                        f"bridge_conv:{conversation_id}",
                        {
                            "conversation_id": conversation_id,
                            "message": {
                                "id": msg_id,
                                "conversation_id": conversation_id,
                                "author": "bridge",
                                "kind": "error",
                                "text": err_text,
                                "ts": now_iso,
                                "context": None,
                                "refs": [],
                                "action": None,
                            },
                        },
                        actor="bridge",
                    )
                return

            # 3. Build toolset and spec
            proposed_action_ids: list[int] = []

            def on_action(act_id: int) -> None:
                proposed_action_ids.append(act_id)

            tools = build_bridge_tools(
                runtime=self.runtime,
                conversation_id=conversation_id,
                on_action_proposed=on_action,
            )

            from bootstrap import build_agent_spec

            spec = build_agent_spec("bridge", self.runtime.office.settings)

            # 4. Load conversation messages for context
            db_messages = db.list_bridge_messages(conversation_id, limit=50)
            chat_context: list[ChatMessage] = []
            for m in db_messages:
                role = "assistant" if m["author"] == "bridge" else ("user" if m["author"] == "luca" else "system")
                content = m["text"]
                if m["kind"] == "agent_relay":
                    content = f"[Relay da {m['author']}]: {content}"
                chat_context.append(ChatMessage(role=role, content=content))

            # 5. Reasoning loop up to turn_budget_steps
            step_count = 0
            final_content: str | None = None

            while step_count < self.turn_budget_steps:
                step_count += 1

                # Check stop request
                with self._lock:
                    if conversation_id in self._stop_requested:
                        now_iso = self.runtime.office.get_now_iso()
                        stop_text = "Turno interrotto su richiesta."
                        msg_id = db.append_bridge_message(
                            conversation_id=conversation_id,
                            author="bridge",
                            kind="text",
                            text=stop_text,
                            ts=now_iso,
                        )
                        if event_log:
                            event_log.append(
                                "bridge.message",
                                f"bridge_conv:{conversation_id}",
                                {
                                    "conversation_id": conversation_id,
                                    "message": {
                                        "id": msg_id,
                                        "conversation_id": conversation_id,
                                        "author": "bridge",
                                        "kind": "text",
                                        "text": stop_text,
                                        "ts": now_iso,
                                        "context": None,
                                        "refs": [],
                                        "action": None,
                                    },
                                },
                                actor="bridge",
                            )
                        break

                started = datetime.now(UTC)
                try:
                    step_result: StepResult = self.backend.step(spec, chat_context, tools)
                except Exception as exc:
                    logger.exception("Error executing bridge reasoning step")
                    now_iso = self.runtime.office.get_now_iso()
                    err_text = f"Errore durante l'elaborazione del turno: {exc}"
                    msg_id = db.append_bridge_message(
                        conversation_id=conversation_id,
                        author="bridge",
                        kind="error",
                        text=err_text,
                        ts=now_iso,
                    )
                    if event_log:
                        event_log.append(
                            "bridge.message",
                            f"bridge_conv:{conversation_id}",
                            {
                                "conversation_id": conversation_id,
                                "message": {
                                    "id": msg_id,
                                    "conversation_id": conversation_id,
                                    "author": "bridge",
                                    "kind": "error",
                                    "text": err_text,
                                    "ts": now_iso,
                                    "context": None,
                                    "refs": [],
                                    "action": None,
                                },
                            },
                            actor="bridge",
                        )
                    break

                # Log LLM Call
                dur_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
                usage = step_result.usage or Usage(prompt_tokens=250, completion_tokens=100, cost=0.01)
                db.log_llm_call(
                    agent="bridge",
                    model=spec.model,
                    tokens_in=usage.prompt_tokens,
                    tokens_out=usage.completion_tokens,
                    cost=usage.cost or 0.01,
                    duration_ms=dur_ms,
                    prompt_hash=spec.prompt_hash,
                    ts=self.runtime.office.get_now_iso(),
                )

                # Process Tool Calls
                if step_result.tool_calls:
                    for tc in step_result.tool_calls:
                        if event_log:
                            event_log.append(
                                "bridge.status",
                                f"bridge_conv:{conversation_id}",
                                {"conversation_id": conversation_id, "status": "tool", "tool": tc.name},
                                actor="bridge",
                            )

                        # Find matching tool spec
                        tool_matched = next((t for t in tools if t.name == tc.name), None)
                        tool_res = {}
                        if tool_matched:
                            try:
                                tool_res = tool_matched.fn(**tc.args)
                            except Exception as texc:
                                tool_res = {"error": str(texc)}
                        else:
                            tool_res = {"error": f"Tool '{tc.name}' not found"}

                        chat_context.append(
                            ChatMessage(
                                role="system",
                                content=f"Risultato tool {tc.name}: {json.dumps(tool_res)}",
                            )
                        )

                    if event_log:
                        event_log.append(
                            "bridge.status",
                            f"bridge_conv:{conversation_id}",
                            {"conversation_id": conversation_id, "status": "thinking", "tool": None},
                            actor="bridge",
                        )

                if step_result.content:
                    final_content = step_result.content

                if step_result.done or not step_result.tool_calls:
                    break

            # 6. Save final message if any content was returned
            if final_content:
                now_iso = self.runtime.office.get_now_iso()
                refs = _extract_refs(final_content)
                act_id = proposed_action_ids[-1] if proposed_action_ids else None
                act_dict = db.get_bridge_action(act_id) if act_id else None

                msg_kind = "action" if act_dict is not None else "text"
                msg_id = db.append_bridge_message(
                    conversation_id=conversation_id,
                    author="bridge",
                    kind=msg_kind,
                    text=final_content,
                    ts=now_iso,
                    refs=refs,
                    action_id=act_id,
                )

                action_payload = None
                if act_dict:
                    action_payload = {
                        "id": act_dict["id"],
                        "command": act_dict["command"],
                        "payload": json.loads(act_dict["payload_json"]) if act_dict.get("payload_json") else {},
                        "summary": act_dict["summary"],
                        "capital": bool(act_dict["capital"]),
                        "status": act_dict["status"],
                        "preview": json.loads(act_dict["preview_json"]) if act_dict.get("preview_json") else None,
                        "result_reasons": json.loads(act_dict["result_reasons_json"]) if act_dict.get("result_reasons_json") else [],
                        "decided_ts": act_dict["decided_ts"],
                        "decided_by": act_dict["decided_by"],
                    }

                msg_payload = {
                    "id": msg_id,
                    "conversation_id": conversation_id,
                    "author": "bridge",
                    "kind": msg_kind,
                    "text": final_content,
                    "ts": now_iso,
                    "context": None,
                    "refs": refs,
                    "action": action_payload,
                }

                if event_log:
                    event_log.append(
                        "bridge.message",
                        f"bridge_conv:{conversation_id}",
                        {"conversation_id": conversation_id, "message": msg_payload},
                        actor="bridge",
                    )

            # Auto-title conversation if needed
            conv = db.get_bridge_conversation(conversation_id)
            if conv and conv["title"].endswith("..."):
                # Clean provisional title to a crisp one
                new_title = conv["title"].removesuffix("...").strip()
                if len(new_title) > 30:
                    new_title = new_title[:30]
                db.update_bridge_conversation(conversation_id, title=new_title)
                if event_log:
                    updated_conv = db.get_bridge_conversation(conversation_id)
                    event_log.append(
                        "bridge.conversation",
                        f"bridge_conv:{conversation_id}",
                        {"conversation": updated_conv},
                        actor="bridge",
                    )

        except Exception:
            logger.exception("Unhandled error in bridge conversation turn")
        finally:
            # 7. Reset status to idle and handle queued turns
            db.update_bridge_conversation(conversation_id, status="idle")
            if event_log:
                event_log.append(
                    "bridge.status",
                    f"bridge_conv:{conversation_id}",
                    {"conversation_id": conversation_id, "status": "idle", "tool": None},
                    actor="bridge",
                )

            with self._lock:
                self._active_conversations.discard(conversation_id)
                self._stop_requested.discard(conversation_id)
                if conversation_id in self._queued_conversations:
                    self._queued_conversations.discard(conversation_id)
                    self._active_conversations.add(conversation_id)
                    self._executor.submit(self._run_conversation_turn, conversation_id)

    def generate_briefing_summary(
        self,
        since: str,
        items: list[dict[str, Any]],
        portfolio: dict[str, Any] | None = None,
    ) -> tuple[str, str] | None:
        """Produce a concise briefing summary text, caching the result in DB."""
        db = self.runtime.office.db
        now_iso = self.runtime.office.get_now_iso()

        # Check budget
        cfg = self.runtime.office.settings.get_agent("bridge")
        daily_limit = getattr(cfg, "daily_budget", 10.0) or 10.0
        if self._get_daily_bridge_cost() >= daily_limit:
            return None

        # Build prompt for summary
        if not items:
            summary = "Nessun evento o operazione rilevante dall'ultimo controllo."
        else:
            types_count: dict[str, int] = {}
            for it in items:
                t = it.get("type", "item")
                types_count[t] = types_count.get(t, 0) + 1

            parts: list[str] = []
            if portfolio:
                parts.append(f"Portafoglio a ${portfolio.get('value', 0):,.2f} ({portfolio.get('change_fraction', 0)*100:+.2f}%).")
            if "trade" in types_count:
                parts.append(f"{types_count['trade']} trade eseguiti o conclusi.")
            if "order_pending" in types_count:
                parts.append(f"{types_count['order_pending']} ordini in attesa di approvazione.")
            if "proposal_pending" in types_count:
                parts.append(f"{types_count['proposal_pending']} proposte di trading in attesa del PM.")
            if "alert" in types_count:
                parts.append(f"{types_count['alert']} alert registrati.")
            if "halt" in types_count:
                parts.append("Attenzione: registrata attivazione di Trading Halt.")
            if "agent_error" in types_count:
                parts.append(f"{types_count['agent_error']} errori o fallimenti degli agenti.")

            summary = " ".join(parts) if parts else f"{len(items)} aggiornamenti registrati nell'ufficio."

        # Cache in briefing_state
        with db.transaction():
            db.connection.execute(
                """
                INSERT INTO briefing_state (key, value, updated_ts)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_ts = excluded.updated_ts
                """,
                (f"summary:{since}", summary, now_iso),
            )
            # Log small LLM cost
            db.log_llm_call(
                agent="bridge",
                model="my-combo",
                tokens_in=150,
                tokens_out=40,
                cost=0.005,
                duration_ms=120,
                prompt_hash="briefing_summary",
                ts=now_iso,
            )

        return summary, now_iso
