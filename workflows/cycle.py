"""Cycle runner driving a single ticker analysis cycle."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from agents.backend import (
    AgentBackend,
    AgentSpec,
    ChatMessage,
    OutgoingMessage,
    StepResult,
    ToolCall,
)
from config.office_settings import OfficeSettings
from execution.order_draft import OrderDraft
from execution.order_flow import OrderFlow, Outcome
from execution.risk_gate import RiskGateContext, RiskGateLimits
from storage.office_db import OfficeDB, utc_now_iso
from storage.registry import LlmCallRecord, RegistryWriter
from tools.environment import AgentEnvironment
from workflows.scheduling import TaskSource, _add_trading_days

logger = logging.getLogger(__name__)

_ANALYST_AGENTS = (
    "sentiment_analyst",
    "technical_analyst",
    "fundamental_analyst",
    "risk_analyst",
)


class CycleRunner:
    """Orchestrates an analysis cycle on a single ticker from opening to PM decision."""

    def __init__(
        self,
        db: OfficeDB,
        backend: AgentBackend,
        env: AgentEnvironment,
        order_flow: OrderFlow,
        clock: Callable[[], datetime] | datetime | None,
        settings: OfficeSettings,
        registry: RegistryWriter | None,
        ticker: str,
        cycle_id: int,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.db = db
        self.backend = backend
        self.env = env
        self.order_flow = order_flow
        self.clock = clock
        self.settings = settings
        self.registry = registry
        self.ticker = ticker.upper().strip()
        self.cycle_id = cycle_id
        self.sleep_fn = sleep_fn

        self._last_seen_message_id: dict[int, int] = {}
        self._init_last_seen()

    def get_now(self) -> datetime:
        if self.clock is not None:
            t = self.clock() if callable(self.clock) else self.clock
        else:
            t = datetime.now(UTC)
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        return t

    def get_now_iso(self) -> str:
        return self.get_now().isoformat().replace("+00:00", "Z")

    def _init_last_seen(self) -> None:
        """Initialize seen message pointers so analysts only read new messages."""
        pm_chat_id = self.db.get_or_create_chat("portfolio_manager", self.ticker)
        # For PM, we want the opening message to be unread, so last_seen is set
        # to the maximum message ID *before* the current cycle's messages.
        prev_pm_msgs = self.db.connection.execute(
            """
            SELECT COALESCE(MAX(id), 0) as max_id FROM messages
            WHERE chat_id = ? AND (cycle_id IS NULL OR cycle_id != ?)
            """,
            (pm_chat_id, self.cycle_id),
        ).fetchone()
        self._last_seen_message_id[pm_chat_id] = int(prev_pm_msgs["max_id"]) if prev_pm_msgs else 0

        # For analysts, set to current max message ID so only new messages in this cycle trigger them
        for agent in _ANALYST_AGENTS:
            chat_id = self.db.get_or_create_chat(agent, self.ticker)
            row = self.db.connection.execute(
                "SELECT COALESCE(MAX(id), 0) as max_id FROM messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            self._last_seen_message_id[chat_id] = int(row["max_id"]) if row else 0

    def _get_agent_spec(self, agent_name: str) -> AgentSpec:
        try:
            cfg = self.settings.get_agent(agent_name)
            model = cfg.model
            endpoint = cfg.endpoint
            effort = cfg.effort
            prompt = ""
            if cfg.system_prompt_path:
                try:
                    with open(cfg.system_prompt_path, encoding="utf-8") as f:
                        prompt = f.read()
                except OSError:
                    pass
        except KeyError:
            model = "my-combo"
            endpoint = "http://100.74.207.0:20128/v1"
            effort = "medium"
            prompt = ""

        role = agent_name
        reg = self.db.get_agent(agent_name)
        if reg and reg.get("role"):
            role = reg["role"]

        return AgentSpec(
            name=agent_name,
            role=role,
            model=model,
            endpoint=endpoint,
            effort=effort,
            system_prompt=prompt,
        )

    def _build_chat_context(self, agent_name: str, chat_id: int) -> list[ChatMessage]:
        rows = self.db.list_messages(chat_id)
        context: list[ChatMessage] = []
        for r in rows:
            author = r["author"]
            text = r["text"]
            if author == agent_name:
                role = "assistant"
            elif author == "system":
                role = "system"
            else:
                role = "user"
            context.append(ChatMessage(role=role, content=text, name=author))
        return context

    def _get_budget_used(self) -> dict[str, int]:
        row = self.db.get_cycle(self.cycle_id)
        if not row or not row.get("budget_used_json"):
            return {"messages": 0, "subagents": 0, "total": 0}
        try:
            return json.loads(row["budget_used_json"])
        except Exception:
            return {"messages": 0, "subagents": 0, "total": 0}

    def _increment_budget(self, category: str) -> None:
        budget = self._get_budget_used()
        budget[category] = budget.get(category, 0) + 1
        budget["total"] = budget.get("total", 0) + 1
        self.db.connection.execute(
            "UPDATE cycles SET budget_used_json = ? WHERE id = ?",
            (json.dumps(budget), self.cycle_id),
        )

    def _ensure_future_scheduled_task(self) -> None:
        now_ts = self.get_now_iso()
        sym = self.ticker.upper().strip()
        row = self.db.connection.execute(
            """
            SELECT id FROM scheduled_tasks
            WHERE (UPPER(chat) = ? OR UPPER(data_json) LIKE ?)
              AND status = 'pending'
              AND when_ts > ?
            LIMIT 1
            """,
            (sym, f"%{sym}%", now_ts),
        ).fetchone()
        if not row:
            next_date = _add_trading_days(self.get_now().date(), 1, self.env.calendar)
            next_dt = datetime.combine(next_date, datetime.min.time(), tzinfo=UTC)
            next_iso = next_dt.isoformat().replace("+00:00", "Z")
            self.db.enqueue_scheduled_task(
                agent="portfolio_manager",
                chat=sym,
                when_ts=next_iso,
                source=TaskSource.AGENT.value,
                reason=f"Controllo programmato successivo su {sym}",
                data={"ticker": sym},
            )

    def _process_order_flow(self, action: str, state: dict[str, Any]) -> Outcome:
        draft_dict = state.get("draft")
        if not draft_dict:
            return Outcome(
                status="deferred",
                reasons=("Nessuna bozza dell'ordine valida presente nello stato",),
                action=action,
            )

        draft = OrderDraft(
            symbol=draft_dict["symbol"],
            side=draft_dict["side"],
            entry=Decimal(str(draft_dict["entry"])),
            stop=Decimal(str(draft_dict["stop"])) if draft_dict.get("stop") is not None else None,
            take_profit=(
                Decimal(str(draft_dict["take_profit"]))
                if draft_dict.get("take_profit") is not None
                else None
            ),
            quantity=Decimal(str(draft_dict["quantity"])),
            risk_reward=(
                Decimal(str(draft_dict["risk_reward"]))
                if draft_dict.get("risk_reward") is not None
                else None
            ),
            risk_amount=(
                Decimal(str(draft_dict["risk_amount"]))
                if draft_dict.get("risk_amount") is not None
                else None
            ),
            notional=Decimal(str(draft_dict["notional"])),
        )

        account = self.env.broker_reader.get_account()
        positions = self.env.broker_reader.get_positions()
        equity_val = getattr(account, "equity", None)
        if equity_val is None and isinstance(account, dict):
            equity_val = account.get("equity")
        equity = Decimal(str(equity_val or "100000.0"))

        cash_val = getattr(account, "cash", None)
        if cash_val is None and isinstance(account, dict):
            cash_val = account.get("cash")
        cash = Decimal(str(cash_val or "50000.0"))

        pos_dict: dict[str, Decimal] = {}
        for p in positions:
            sym = getattr(p, "symbol", "") if hasattr(p, "symbol") else p.get("symbol", "")
            mv = getattr(p, "market_value", None)
            if mv is None:
                qty = Decimal(str(getattr(p, "quantity", 0)))
                price = Decimal(
                    str(getattr(p, "current_price", 0) or getattr(p, "average_entry_price", 0))
                )
                mv = qty * price
            pos_dict[sym.upper()] = Decimal(str(mv))

        sector_map: dict[str, str] = {}
        rows = self.db.connection.execute("SELECT symbol, sector FROM securities").fetchall()
        for r in rows:
            if r["sector"]:
                sector_map[r["symbol"].upper()] = r["sector"]

        limits = RiskGateLimits(
            max_risk_per_trade=Decimal(str(self.settings.limits.max_risk_per_trade_fraction)),
            max_position_size=Decimal(str(self.settings.limits.max_position_fraction)),
            max_sector_exposure=Decimal(str(self.settings.limits.max_sector_fraction)),
            max_open_positions=self.settings.limits.max_open_positions,
            min_cash_reserve=Decimal(str(self.settings.limits.min_cash_reserve_fraction)),
            min_risk_reward=Decimal(str(self.settings.limits.min_risk_reward_ratio)),
            earnings_blackout_trading_days=self.settings.limits.earnings_embargo_days,
        )

        gate_ctx = RiskGateContext(
            equity=equity,
            cash=cash,
            positions=pos_dict,
            sector_map=sector_map,
            open_positions_count=len(positions),
            limits=limits,
            today=self.get_now().date(),
        )

        return self.order_flow.process_accepted_order(
            ticker=self.ticker,
            action=action,
            draft=draft,
            ctx=gate_ctx,
        )

    def _step_agent(self, agent_name: str, chat_id: int) -> StepResult | None:
        """Execute a step for agent with 2 retries on transient errors."""
        attempt = 0
        wait = 0.5
        while True:
            attempt += 1
            try:
                chat_context = self._build_chat_context(agent_name, chat_id)
                tools = self.env.tools_for(agent_name, chat_id=chat_id, cycle_id=self.cycle_id)
                agent_spec = self._get_agent_spec(agent_name)

                result = self.backend.step(agent_spec, chat_context, tools)

                if self.registry:
                    usage = result.usage
                    tokens_in = usage.prompt_tokens if usage else 0
                    tokens_out = usage.completion_tokens if usage else 0
                    cost = usage.cost if usage and usage.cost is not None else 0.0
                    self.registry.enqueue(
                        LlmCallRecord(
                            agent=agent_name,
                            model=agent_spec.model,
                            tokens_in=tokens_in,
                            tokens_out=tokens_out,
                            cost=cost,
                            chat_id=chat_id,
                            prompt_hash=agent_spec.prompt_hash,
                            ts=self.get_now_iso(),
                        )
                    )
                return result
            except Exception as exc:
                if attempt <= 2:
                    self.sleep_fn(wait)
                    wait *= 2.0
                    continue
                # All 2 retries exhausted
                if agent_name in ("pm", "portfolio_manager"):
                    # PM failure -> deterministic Rimando + inbox
                    self.db.add_inbox(
                        "error",
                        f"Fallimento PM su {self.ticker}: {exc}",
                        ts=self.get_now_iso(),
                    )
                    pm_chat_id = self.db.get_or_create_chat("portfolio_manager", self.ticker)
                    self.db.append_message(
                        chat_id=pm_chat_id,
                        author="system",
                        text=f"Rimando: fallimento persistente del Portfolio Manager ({exc}).",
                        kind="original",
                        cycle_id=self.cycle_id,
                        ts=self.get_now_iso(),
                    )
                    return None
                else:
                    # Specialist failure -> write error in chat and notify PM so cycle continues
                    err_msg_id = self.db.append_message(
                        chat_id=chat_id,
                        author=agent_name,
                        text=f"Errore durante l'elaborazione dell'agente {agent_name}: {exc}",
                        kind="original",
                        cycle_id=self.cycle_id,
                        ts=self.get_now_iso(),
                    )
                    self._last_seen_message_id[chat_id] = max(
                        self._last_seen_message_id.get(chat_id, 0), err_msg_id
                    )

                    # Notify PM chat so PM knows specialist encountered an error and cycle can continue
                    pm_chat_id = self.db.get_or_create_chat("portfolio_manager", self.ticker)
                    self.db.append_message(
                        chat_id=pm_chat_id,
                        author=agent_name,
                        text=f"Segnalazione errore da {agent_name}: {exc}",
                        kind="original",
                        cycle_id=self.cycle_id,
                        ts=self.get_now_iso(),
                    )
                    return None

    def run(self) -> str:
        """Run the cycle loop until PM decides or cycle budget is exhausted."""
        pm_chat_id = self.db.get_or_create_chat("portfolio_manager", self.ticker)

        while True:
            # 1. Check budget exhaustion
            budget = self._get_budget_used()
            if budget.get("total", 0) >= self.settings.budgets.cycle_budget:
                self.db.add_inbox(
                    "warning",
                    f"Budget ciclo esaurito per {self.ticker} (utilizzati: {budget.get('total')})",
                    ts=self.get_now_iso(),
                )
                self.db.append_message(
                    chat_id=pm_chat_id,
                    author="system",
                    text=f"Rimando deterministico: budget del ciclo ({self.settings.budgets.cycle_budget}) esaurito.",
                    kind="original",
                    cycle_id=self.cycle_id,
                    ts=self.get_now_iso(),
                )
                self._ensure_future_scheduled_task()
                self.db.close_cycle(self.cycle_id, outcome="rimando", closed_ts=self.get_now_iso())
                return "rimando"

            # 2. Check PM decision in ticker_state
            st_row = self.db.get_ticker_state(self.ticker)
            if st_row and st_row.get("state_json"):
                try:
                    state_data = json.loads(st_row["state_json"])
                except Exception:
                    state_data = {}
                decision = state_data.get("decision")
                if decision and isinstance(decision, dict):
                    status = decision.get("status")
                    action = decision.get("action")
                    if status in ("accepted", "deferred"):
                        if action == "defer":
                            self._ensure_future_scheduled_task()
                            self.db.close_cycle(
                                self.cycle_id, outcome="deferred", closed_ts=self.get_now_iso()
                            )
                            return "deferred"
                        elif action in ("buy", "sell"):
                            outcome = self._process_order_flow(action, state_data)
                            self._ensure_future_scheduled_task()
                            if (
                                outcome.is_submitted
                                or outcome.is_queued
                                or outcome.is_pending
                            ):
                                self.db.close_cycle(
                                    self.cycle_id,
                                    outcome="accepted",
                                    closed_ts=self.get_now_iso(),
                                )
                                return "accepted"
                            else:
                                reasons_str = (
                                    "; ".join(outcome.reasons)
                                    if outcome.reasons
                                    else outcome.status
                                )
                                self.db.append_message(
                                    chat_id=pm_chat_id,
                                    author="system",
                                    text=(
                                        f"Rimando: ordine non eseguito ({outcome.status}). "
                                        f"Motivo: {reasons_str}"
                                    ),
                                    kind="original",
                                    cycle_id=self.cycle_id,
                                    ts=self.get_now_iso(),
                                )
                                self.db.close_cycle(
                                    self.cycle_id,
                                    outcome="rimando",
                                    closed_ts=self.get_now_iso(),
                                )
                                return "rimando"

            # 3. Find agents with unread messages from other authors
            agents_to_step: list[tuple[str, int]] = []

            # Check analysts first
            for analyst in _ANALYST_AGENTS:
                c_id = self.db.get_or_create_chat(analyst, self.ticker)
                last_seen = self._last_seen_message_id.get(c_id, 0)
                row = self.db.connection.execute(
                    """
                    SELECT COALESCE(MAX(id), 0) as max_id FROM messages
                    WHERE chat_id = ? AND id > ? AND author != ?
                    """,
                    (c_id, last_seen, analyst),
                ).fetchone()
                if row and row["max_id"] > last_seen:
                    agents_to_step.append((analyst, c_id))

            # Check PM
            pm_last_seen = self._last_seen_message_id.get(pm_chat_id, 0)
            pm_row = self.db.connection.execute(
                """
                SELECT COALESCE(MAX(id), 0) as max_id FROM messages
                WHERE chat_id = ? AND id > ? AND author NOT IN ('portfolio_manager', 'pm')
                """,
                (pm_chat_id, pm_last_seen),
            ).fetchone()
            if pm_row and pm_row["max_id"] > pm_last_seen:
                agents_to_step.append(("portfolio_manager", pm_chat_id))

            # If no agent has unread messages and PM hasn't decided, finish
            if not agents_to_step:
                # Nobody has unread messages -> default Rimando to prevent hanging
                self._ensure_future_scheduled_task()
                self.db.close_cycle(self.cycle_id, outcome="rimando", closed_ts=self.get_now_iso())
                return "rimando"

            # Step agents in turns
            for agent_name, chat_id in agents_to_step:
                # Update last seen before or after step
                cur_max_row = self.db.connection.execute(
                    "SELECT COALESCE(MAX(id), 0) as max_id FROM messages WHERE chat_id = ?",
                    (chat_id,),
                ).fetchone()
                cur_max = int(cur_max_row["max_id"]) if cur_max_row else 0
                self._last_seen_message_id[chat_id] = cur_max

                step_res = self._step_agent(agent_name, chat_id)
                if step_res is None:
                    if agent_name in ("pm", "portfolio_manager"):
                        self._ensure_future_scheduled_task()
                        self.db.close_cycle(
                            self.cycle_id, outcome="rimando", closed_ts=self.get_now_iso()
                        )
                        return "rimando"
                    continue

                # Execute tool calls
                executed_send_keys: set[tuple[str, str, str]] = set()
                tools = self.env.tools_for(agent_name, chat_id=chat_id, cycle_id=self.cycle_id)
                tool_map = {t.name: t for t in tools}

                for tc in step_res.tool_calls:
                    if tc.name in tool_map:
                        try:
                            tool_map[tc.name].execute(tc)
                            if tc.name == "send_message" and isinstance(tc.args, dict):
                                to_ag = str(tc.args.get("to_agent", ""))
                                top = str(tc.args.get("ticker_or_theme", ""))
                                txt = str(tc.args.get("text", ""))
                                executed_send_keys.add((to_ag, top, txt))
                        except Exception as e:
                            logger.warning(f"Error executing tool {tc.name}: {e}")

                # Deliver outgoing messages not already sent via tool_call
                for out in step_res.outgoing_messages:
                    if (out.to_agent, out.chat, out.text) not in executed_send_keys:
                        dest_chat_id = self.db.get_or_create_chat(out.to_agent, out.chat)
                        self.db.append_message(
                            chat_id=dest_chat_id,
                            author=agent_name,
                            text=out.text,
                            kind="original",
                            cycle_id=self.cycle_id,
                            ts=self.get_now_iso(),
                        )
                        self._increment_budget("messages")

                # If content text is returned with no tool calls and no outgoing messages, log it
                if (
                    step_res.content
                    and not step_res.tool_calls
                    and not step_res.outgoing_messages
                ):
                    self.db.append_message(
                        chat_id=chat_id,
                        author=agent_name,
                        text=step_res.content,
                        kind="original",
                        cycle_id=self.cycle_id,
                        ts=self.get_now_iso(),
                    )
