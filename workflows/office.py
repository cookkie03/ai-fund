"""Office engine: scheduling loop, task delivery, concurrency, and cycle coordination."""

from __future__ import annotations

import concurrent.futures
import inspect
import json
import logging
import threading
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from agents.backend import AgentBackend, AgentSpec, ChatMessage, StepResult
from config.office_settings import OfficeSettings
from execution.order_flow import OrderFlow, SystemHalt
from storage.office_db import OfficeDB, utc_now_iso
from storage.registry import LlmCallRecord, RegistryWriter
from tools.environment import AgentEnvironment
from workflows.cycle import CycleRunner
from workflows.scheduling import (
    DueCursor,
    ScheduledTask,
    TaskSource,
    due_tasks,
    merge_tasks,
    record_task_failure,
    translate_task,
)

logger = logging.getLogger(__name__)


def _to_scheduled_task(raw: Any) -> ScheduledTask:
    if isinstance(raw, ScheduledTask):
        return raw
    if isinstance(raw, dict):
        src_val = raw.get("source", "agent")
        try:
            source = TaskSource(src_val)
        except ValueError:
            source = TaskSource.AGENT

        when_raw = raw.get("when") or raw.get("when_ts")
        if isinstance(when_raw, str):
            when_dt = datetime.fromisoformat(when_raw.replace("Z", "+00:00"))
        elif isinstance(when_raw, datetime):
            when_dt = when_raw
        else:
            when_dt = datetime.now(UTC)
        if when_dt.tzinfo is None:
            when_dt = when_dt.replace(tzinfo=UTC)

        next_raw = raw.get("next_attempt_ts") or raw.get("next_attempt_not_before")
        next_dt = None
        if isinstance(next_raw, str):
            next_dt = datetime.fromisoformat(next_raw.replace("Z", "+00:00"))
            if next_dt.tzinfo is None:
                next_dt = next_dt.replace(tzinfo=UTC)
        elif isinstance(next_raw, datetime):
            next_dt = next_raw if next_raw.tzinfo else next_raw.replace(tzinfo=UTC)

        data = raw.get("data")
        if data is None and raw.get("data_json"):
            try:
                data = json.loads(raw["data_json"])
            except Exception:
                data = {}

        return ScheduledTask(
            agent=raw.get("agent", "portfolio_manager"),
            chat=raw.get("chat", ""),
            when=when_dt,
            source=source,
            reason=raw.get("reason", ""),
            data=data or {},
            task_id=str(raw.get("id") or raw.get("task_id", "")),
            attempts=int(raw.get("attempts", 0)),
            next_attempt_not_before=next_dt,
        )
    raise TypeError(f"Cannot convert {type(raw)} to ScheduledTask")


class Office:
    """The Agent Office engine coordinating triggers, cycles, and agents."""

    def __init__(
        self,
        db: OfficeDB,
        backend: AgentBackend,
        env_factory: Callable[..., AgentEnvironment] | AgentEnvironment,
        order_flow: OrderFlow,
        clock: Callable[[], datetime] | datetime | None = None,
        settings: OfficeSettings | None = None,
        registry: RegistryWriter | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.db = db
        self.backend = backend
        self.env_factory = env_factory
        self.order_flow = order_flow
        self.clock = clock
        self.settings = settings or OfficeSettings()
        self.registry = registry
        self.sleep_fn = sleep_fn

        self.halt = getattr(order_flow, "halt", None) or SystemHalt(db)
        self._stop_event = threading.Event()
        self._cursor = DueCursor()
        self._lock = threading.RLock()
        self._active_cycles_by_ticker: dict[str, int] = {}

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

    def get_env(self, cycle_id: int | None = None) -> AgentEnvironment:
        if callable(self.env_factory):
            try:
                return self.env_factory(cycle_id)
            except TypeError:
                return self.env_factory()
        return self.env_factory

    def _is_pm_agent(self, agent_name: str) -> bool:
        norm = agent_name.lower().strip()
        return norm in ("pm", "portfolio_manager")

    def _is_market_analyst(self, agent_name: str) -> bool:
        norm = agent_name.lower().strip()
        return norm in ("market", "market_analyst")

    def _compact_pm_chat(self, chat_id: int, ticker: str, cycle_id: int) -> None:
        now_iso = self.get_now_iso()
        prev_row = self.db.connection.execute(
            """
            SELECT id, closed_ts, outcome FROM cycles
            WHERE ticker = ? AND id != ?
            ORDER BY id DESC LIMIT 1
            """,
            (ticker, cycle_id),
        ).fetchone()

        if prev_row:
            prev_closed = prev_row["closed_ts"] or "sconosciuto"
            summary_text = (
                f"[Compattazione] Ciclo #{prev_row['id']} terminato: {prev_closed} "
                f"(esito: {prev_row['outcome']}). Inizio ciclo attuale #{cycle_id}: {now_iso}."
            )
        else:
            summary_text = f"[Compattazione] Inizio primo ciclo #{cycle_id}: {now_iso}."

        self.db.compact_chat(
            chat_id=chat_id,
            summary_text=summary_text,
            author="system",
            cycle_id=cycle_id,
            ts=now_iso,
        )

    def _build_pm_opening_prompt(self, task: ScheduledTask, ticker: str) -> str:
        base_prompt = translate_task(task)
        extras: list[str] = []

        # Latest sector view
        sec_row = self.db.connection.execute(
            "SELECT sector FROM securities WHERE UPPER(symbol) = UPPER(?)",
            (ticker,),
        ).fetchone()
        sector = sec_row["sector"] if sec_row and sec_row["sector"] else None

        st_row = self.db.get_ticker_state(ticker)
        st_data = json.loads(st_row["state_json"]) if st_row and st_row.get("state_json") else {}

        sector_view = st_data.get("sector_view")
        if not sector_view and sector:
            perf_row = self.db.connection.execute(
                "SELECT perf_json FROM sector_performance WHERE sector = ? ORDER BY ts DESC LIMIT 1",
                (sector,),
            ).fetchone()
            if perf_row:
                sector_view = perf_row["perf_json"]

        if sector_view:
            extras.append(f"Visione di settore ({sector or 'macro'}): {sector_view}")

        # Deterministic outcome of previous decision
        prev_decision = st_data.get("decision")
        if prev_decision and isinstance(prev_decision, dict):
            act = prev_decision.get("action", "")
            stat = prev_decision.get("status", "")
            rsn = prev_decision.get("reason", "")
            extras.append(f"Esito decisione precedente: {act} ({stat}) - {rsn}")
        else:
            extras.append("Esito decisione precedente: nessuna decisione precedente registrata.")

        extras.append("Puoi formulare una lezione di una riga sulla decisione precedente.")

        return base_prompt + "\n\n" + "\n".join(extras)

    def _activate_market_analyst(self, task: ScheduledTask) -> None:
        """Run Market Analyst standalone activation on theme chat."""
        theme = task.chat.strip()
        chat_id = self.db.get_or_create_chat("market_analyst", theme)
        now_iso = self.get_now_iso()

        prompt = translate_task(task)
        self.db.append_message(
            chat_id=chat_id,
            author="system",
            text=prompt,
            kind="original",
            ts=now_iso,
        )

        env = self.get_env()
        budget_limit = self.settings.budgets.market_analyst_activation_budget
        budget_used = 0

        # Monitored tickers: watchlist + portfolio
        watchlist_tickers = {w["ticker"].upper() for w in self.db.list_watchlist()}
        positions = env.broker_reader.get_positions()
        portfolio_tickers = {
            (getattr(p, "symbol", "") if hasattr(p, "symbol") else p.get("symbol", "")).upper()
            for p in positions
        }
        monitored = watchlist_tickers | portfolio_tickers

        while budget_used < budget_limit:
            budget_used += 1
            tools = env.tools_for("market_analyst", chat_id=chat_id)
            tool_map = {t.name: t for t in tools}

            msgs = self.db.list_messages(chat_id)
            chat_context = [
                ChatMessage(
                    role="assistant" if m["author"] == "market_analyst" else "user",
                    content=m["text"],
                    name=m["author"],
                )
                for m in msgs
            ]

            spec = AgentSpec(
                name="market_analyst",
                role="market_analyst",
                model=self.settings.get_agent("market_analyst").model,
                endpoint=self.settings.get_agent("market_analyst").endpoint,
                effort=self.settings.get_agent("market_analyst").effort,
            )

            try:
                res: StepResult = self.backend.step(spec, chat_context, tools)
            except Exception as e:
                logger.warning(f"Market analyst step failed: {e}")
                break

            # Execute tools
            for tc in res.tool_calls:
                if tc.name in tool_map:
                    try:
                        tool_map[tc.name].execute(tc)
                    except Exception as e:
                        logger.warning(f"Error in market analyst tool {tc.name}: {e}")

            # Check messages to PM
            all_outgoing = list(res.outgoing_messages)
            for tc in res.tool_calls:
                if tc.name == "send_message" and isinstance(tc.args, dict):
                    all_outgoing.append(
                        OutgoingMessage(
                            to_agent=str(tc.args.get("to_agent", "")),
                            chat=str(tc.args.get("ticker_or_theme", "")),
                            text=str(tc.args.get("text", "")),
                        )
                    )

            for out in all_outgoing:
                if self._is_pm_agent(out.to_agent):
                    # Check which monitored tickers are touched
                    touched: set[str] = set()
                    out_chat = out.chat.upper().strip()
                    if out_chat in monitored:
                        touched.add(out_chat)
                    for sym in monitored:
                        if sym in out.text.upper():
                            touched.add(sym)

                    # Produce scheduled task source=market_message per ticker
                    for sym in sorted(touched):
                        t_id = self.db.enqueue_scheduled_task(
                            agent="portfolio_manager",
                            chat=sym,
                            when_ts=self.get_now_iso(),
                            source=TaskSource.MARKET_MESSAGE.value,
                            reason=f"Messaggio Market Analyst: {out.text[:80]}",
                            data={"ticker": sym, "market_message": out.text},
                        )
                        # Deliver immediately to open cycle per ticker
                        new_task = ScheduledTask(
                            agent="portfolio_manager",
                            chat=sym,
                            when=self.get_now(),
                            source=TaskSource.MARKET_MESSAGE,
                            reason=f"Messaggio Market Analyst: {out.text[:80]}",
                            data={"ticker": sym, "market_message": out.text},
                            task_id=str(t_id),
                        )
                        self.deliver(new_task)

            if res.done or (not res.tool_calls and not res.outgoing_messages):
                break

    def deliver(self, scheduled_task: Any) -> Any:
        """Deliver a scheduled task. Opens a cycle or appends to an active cycle."""
        if self.halt.is_halted():
            logger.info("Office halted: delivery suppressed")
            return None

        task = _to_scheduled_task(scheduled_task)
        now_iso = self.get_now_iso()

        # If Market Analyst activation outside cycles
        if self._is_market_analyst(task.agent):
            self._activate_market_analyst(task)
            return "market_analyst_activated"

        # Otherwise PM delivery on a ticker
        ticker = task.chat.upper().strip()

        with self._lock:
            # Check if cycle already open on this ticker
            active_cycle = self.db.get_active_cycle(ticker)
            if active_cycle is not None:
                cycle_id = active_cycle["id"]
                pm_chat_id = self.db.get_or_create_chat("portfolio_manager", ticker)
                prompt_text = translate_task(task)
                self.db.append_message(
                    chat_id=pm_chat_id,
                    author="system",
                    text=f"[Nuovo task durante ciclo aperto]\n{prompt_text}",
                    kind="original",
                    cycle_id=cycle_id,
                    ts=now_iso,
                )
                return cycle_id

            # Open a new cycle
            cycle_id = self.db.open_cycle(
                ticker=ticker,
                status="open",
                opened_ts=now_iso,
                budget_used={"messages": 0, "subagents": 0, "total": 0},
            )
            self._active_cycles_by_ticker[ticker] = cycle_id

        try:
            pm_chat_id = self.db.get_or_create_chat("portfolio_manager", ticker)
            self._compact_pm_chat(pm_chat_id, ticker, cycle_id)

            opening_prompt = self._build_pm_opening_prompt(task, ticker)
            self.db.append_message(
                chat_id=pm_chat_id,
                author="system",
                text=opening_prompt,
                kind="original",
                cycle_id=cycle_id,
                ts=now_iso,
            )

            env = self.get_env(cycle_id)
            runner = CycleRunner(
                db=self.db,
                backend=self.backend,
                env=env,
                order_flow=self.order_flow,
                clock=self.clock,
                settings=self.settings,
                registry=self.registry,
                ticker=ticker,
                cycle_id=cycle_id,
                sleep_fn=self.sleep_fn,
            )
            outcome = runner.run()
            return outcome
        finally:
            with self._lock:
                self._active_cycles_by_ticker.pop(ticker, None)

    def run_once(self, now: datetime | None = None) -> list[str]:
        """Perform a single scheduler pass: fetch due tasks, merge, deliver up to max_parallel."""
        if self.halt.is_halted():
            return []

        now_dt = now or self.get_now()
        now_iso = now_dt.isoformat().replace("+00:00", "Z")

        # 1. Fetch pending due tasks
        rows = self.db.due_scheduled_tasks(now_ts=now_iso)
        if not rows:
            return []

        raw_tasks = [_to_scheduled_task(r) for r in rows]

        # 2. Merge queued same-chat tasks
        merged = merge_tasks(raw_tasks)

        # Mark merged tasks in DB
        for m_task in merged:
            if m_task.merged_from:
                primary_id = int(m_task.task_id) if m_task.task_id else None
                for orig_id_str in m_task.merged_from:
                    try:
                        orig_id = int(orig_id_str)
                        if orig_id != primary_id:
                            self.db.mark_scheduled_task(
                                orig_id, status="merged", merged_into=primary_id
                            )
                    except ValueError:
                        pass

        # 3. Filter through due_tasks
        candidate_due, _ = due_tasks(merged, now_dt, self._cursor)
        if not candidate_due:
            return []

        # 4. Deliver up to max_parallel
        batch = candidate_due[: self.settings.max_parallel]
        accepted_ids: set[str] = set()
        outcomes: list[str] = []

        if self.settings.max_parallel > 1 and len(batch) > 1:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.settings.max_parallel
            ) as executor:
                future_map = {executor.submit(self.deliver, task): task for task in batch}
                for fut in concurrent.futures.as_completed(future_map):
                    t = future_map[fut]
                    try:
                        res = fut.result()
                        accepted_ids.add(t.task_id)
                        outcomes.append(str(res))
                        if t.task_id:
                            self.db.mark_scheduled_task(int(t.task_id), status="delivered")
                    except Exception as exc:
                        logger.error(f"Failed delivering task {t.task_id}: {exc}")
                        failed_task = record_task_failure(t, now_dt)
                        next_iso = (
                            failed_task.next_attempt_not_before.isoformat().replace("+00:00", "Z")
                            if failed_task.next_attempt_not_before
                            else None
                        )
                        if t.task_id:
                            self.db.mark_scheduled_task(
                                int(t.task_id), status="failed", next_attempt_ts=next_iso
                            )
        else:
            for t in batch:
                try:
                    res = self.deliver(t)
                    accepted_ids.add(t.task_id)
                    outcomes.append(str(res))
                    if t.task_id:
                        self.db.mark_scheduled_task(int(t.task_id), status="delivered")
                except Exception as exc:
                    logger.error(f"Failed delivering task {t.task_id}: {exc}")
                    failed_task = record_task_failure(t, now_dt)
                    next_iso = (
                        failed_task.next_attempt_not_before.isoformat().replace("+00:00", "Z")
                        if failed_task.next_attempt_not_before
                        else None
                    )
                    if t.task_id:
                        self.db.mark_scheduled_task(
                            int(t.task_id), status="failed", next_attempt_ts=next_iso
                        )

        # 5. Advance cursor on accepted delivery
        _, self._cursor = due_tasks(merged, now_dt, self._cursor, accepted_ids=accepted_ids)

        return outcomes

    def run(self, poll_interval: float = 0.5) -> None:
        """Start scheduler polling loop until stop() is called."""
        self._stop_event.clear()
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
            self._stop_event.wait(timeout=poll_interval)

    def stop(self) -> None:
        """Signal scheduler loop to stop."""
        self._stop_event.set()
