"""Tests for Office engine and CycleRunner: triggers, cycles, LLM steps, order flow, and halt."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from agents.backend import ChatMessage, OutgoingMessage, StepResult, ToolCall
from agents.fake_backend import ScriptedBackend
from config.office_settings import BudgetsConfig, OfficeSettings
from execution.order_flow import OrderFlow, SystemHalt
from storage.office_db import OfficeDB
from storage.registry import RegistryWriter
from tests.fakes.bracket_broker import FakeBracketBroker
from tools.environment import AgentEnvironment
from workflows.office import Office
from workflows.scheduling import ScheduledTask, TaskSource


class FakeMarketData:
    def __init__(self) -> None:
        self._quotes = {
            "AAPL": {"symbol": "AAPL", "price": 150.0, "atr": 2.5},
            "MSFT": {"symbol": "MSFT", "price": 300.0, "atr": 4.0},
        }

    def quote(self, symbol: str) -> dict[str, Any]:
        return self._quotes.get(symbol, {"symbol": symbol, "price": 100.0, "atr": 2.0})

    def ohlcv(self, symbol: str, interval: str = "1d", limit: int = 100) -> list[dict[str, Any]]:
        bars = []
        base = 100.0
        for i in range(35):
            o = base + i
            h = o + 2.0
            low = o - 1.5
            c = o + 1.0
            bars.append(
                {"ts": f"2026-01-{i+1:02d}T00:00:00Z", "o": o, "h": h, "l": low, "c": c, "v": 1000}
            )
        return bars

    def news(
        self, symbol: str | None = None, theme: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        return [{"headline": f"News for {symbol or theme}", "summary": "Sample summary"}]

    def ratings(self, symbol: str) -> list[dict[str, Any]] | dict[str, Any]:
        return [{"firm": "Wall St", "rating": "Buy", "target": 200.0}]

    def insiders(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        return [{"name": "CEO", "transaction": "Buy", "shares": 1000}]

    def financials(self, symbol: str) -> dict[str, Any] | list[dict[str, Any]]:
        return {
            "symbol": symbol,
            "revenue": 1000000,
            "net_income": 200000,
            "ratios": {"pe": 25.0, "debt_to_equity": 0.5},
        }

    def earnings_dates(self, symbol: str) -> list[dict[str, Any]] | dict[str, Any]:
        return [{"date": "2026-04-15", "estimate": 1.50}]

    def macro(self, series_id: str) -> list[dict[str, Any]] | dict[str, Any]:
        return [{"series_id": series_id, "value": 3.2, "date": "2026-01-01"}]

    def econ_calendar(self, limit: int = 20) -> list[dict[str, Any]]:
        return [{"event": "FOMC", "date": "2026-03-20"}]

    def sector_perf(self) -> list[dict[str, Any]] | dict[str, Any]:
        return [{"sector": "Technology", "change_pct": 1.5}]


class FakeBrokerReader:
    def __init__(
        self, equity: Decimal = Decimal("100000"), cash: Decimal = Decimal("50000")
    ) -> None:
        self.equity = equity
        self.cash = cash

    def get_account(self) -> dict[str, Any]:
        return {"equity": float(self.equity), "cash": float(self.cash)}

    def get_positions(self) -> list[dict[str, Any]]:
        return []

    def get_orders(self, query: Any = None) -> list[Any]:
        return []


@pytest.fixture
def db(tmp_path) -> OfficeDB:
    return OfficeDB(tmp_path / "office.db")


@pytest.fixture
def broker() -> FakeBracketBroker:
    return FakeBracketBroker()


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def fake_market_data() -> FakeMarketData:
    return FakeMarketData()


@pytest.fixture
def fake_broker_reader() -> FakeBrokerReader:
    return FakeBrokerReader()


@pytest.fixture
def env(db, fake_market_data, fake_broker_reader, fixed_now) -> AgentEnvironment:
    return AgentEnvironment(
        db=db,
        market_data=fake_market_data,
        broker_reader=fake_broker_reader,
        clock=lambda: fixed_now,
    )


@pytest.fixture
def order_flow(db, broker) -> OrderFlow:
    return OrderFlow(db=db, broker=broker, approval_mode="auto")


def test_deliver_task_opens_cycle_compacts_chat_and_translates_prompt(
    db, broker, env, order_flow, fixed_now
):
    """Test that deliver creates cycle, compacts PM chat, and formats opening prompt with sector view and previous outcome."""
    # Pre-populate securities table and previous cycle
    db.connection.execute(
        "INSERT INTO securities (symbol, name, sector) VALUES ('AAPL', 'Apple Inc.', 'Technology')"
    )

    prev_cycle_id = db.open_cycle("AAPL", status="open", opened_ts="2026-05-30T10:00:00Z")
    db.close_cycle(
        prev_cycle_id,
        outcome="deferred",
        closed_ts="2026-05-30T10:30:00Z",
    )

    # Set prior ticker state decision
    db.set_ticker_state(
        "AAPL",
        {
            "decision": {
                "action": "defer",
                "status": "deferred",
                "reason": "Wait for earnings",
            }
        },
    )

    # Scripted PM that immediately defers
    script = {
        ("portfolio_manager", 0): StepResult(
            tool_calls=[
                ToolCall(
                    id="tc1",
                    name="schedule_next_check",
                    args={"ticker": "AAPL", "when": "2026-06-03T10:00:00Z", "note": "next"},
                ),
                ToolCall(
                    id="tc2",
                    name="defer",
                    args={"ticker": "AAPL", "reason": "Further technical confirmation needed"},
                ),
            ],
            done=True,
        )
    }
    backend = ScriptedBackend(script)

    office = Office(
        db=db,
        backend=backend,
        env_factory=lambda cid: env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )

    task = ScheduledTask(
        agent="portfolio_manager",
        chat="AAPL",
        when=fixed_now,
        source=TaskSource.AGENT,
        reason="Routine weekly review",
        data={"priority": "high"},
    )

    outcome = office.deliver(task)
    assert outcome == "deferred"

    # Check cycles table in DB
    cycles = db.connection.execute(
        "SELECT * FROM cycles WHERE ticker = 'AAPL' ORDER BY id ASC"
    ).fetchall()
    assert len(cycles) == 2
    cur_cycle = cycles[1]
    assert cur_cycle["status"] == "closed"
    assert cur_cycle["outcome"] == "deferred"

    # Check PM chat messages
    pm_chat_id = db.get_or_create_chat("portfolio_manager", "AAPL")
    msgs = db.list_messages(pm_chat_id)

    # Verify summary compaction row
    summaries = [m for m in msgs if m["kind"] == "summary"]
    assert len(summaries) >= 1
    assert "Ciclo #" in summaries[0]["text"]

    # Verify opening prompt contains translated task and previous outcome
    originals = [m for m in msgs if m["kind"] == "original"]
    assert len(originals) >= 1
    opening_text = originals[0]["text"]
    assert "Fonte: Controllo Programmato Agente" in opening_text
    assert "Ticker: AAPL" in opening_text
    assert "Motivo: Routine weekly review" in opening_text
    assert "Esito decisione precedente: defer (deferred)" in opening_text
    assert "Puoi formulare una lezione di una riga" in opening_text


def test_deliver_to_active_cycle_appends_message_without_duplicate_cycle(
    db, broker, env, order_flow, fixed_now
):
    """Test that a task on an already open ticker cycle appends as a message instead of duplicating the cycle."""
    active_cycle_id = db.open_cycle("AAPL", status="open", opened_ts="2026-06-01T09:00:00Z")

    office = Office(
        db=db,
        backend=ScriptedBackend({}),
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )

    task = ScheduledTask(
        agent="portfolio_manager",
        chat="AAPL",
        when=fixed_now,
        source=TaskSource.ALERT_PRICE,
        reason="Price breakout alert",
    )

    ret = office.deliver(task)
    assert ret == active_cycle_id

    # Verify no second cycle was opened
    cycles = db.connection.execute(
        "SELECT * FROM cycles WHERE ticker = 'AAPL' AND status = 'open'"
    ).fetchall()
    assert len(cycles) == 1

    # Verify message appended to PM chat
    pm_chat_id = db.get_or_create_chat("portfolio_manager", "AAPL")
    msgs = db.list_messages(pm_chat_id)
    assert any("[Nuovo task durante ciclo aperto]" in m["text"] for m in msgs)


def test_full_cycle_analysts_turn_and_pm_accept_submits_order(
    db, broker, env, order_flow, fixed_now
):
    """Stories 23, 46, 57, 63: PM sends opening to analysts, analysts suggest and set coeffs, PM accepts, order submitted to broker."""
    # Step sequence:
    # 1. PM Turn 0: sends message to technical and risk analysts
    # 2. Risk analyst Turn 0: sets k_entry & risk_fraction, suggests BUY
    # 3. Technical analyst Turn 0: sets k_stop & k_tp, suggests BUY
    # 4. PM Turn 1: schedules next check and accepts order
    script = {
        ("portfolio_manager", 0): StepResult(
            outgoing_messages=[
                OutgoingMessage(
                    to_agent="risk_analyst",
                    chat="AAPL",
                    text="Risk Analyst, valuta parametri di rischio per AAPL",
                ),
                OutgoingMessage(
                    to_agent="technical_analyst",
                    chat="AAPL",
                    text="Technical Analyst, analizza supporto e resistenze per AAPL",
                ),
            ],
            done=True,
        ),
        ("risk_analyst", 0): StepResult(
            tool_calls=[
                ToolCall(
                    id="t_risk",
                    name="set_coefficients",
                    args={"ticker": "AAPL", "k_entry": 0.5, "risk_fraction": 0.003},
                ),
                ToolCall(
                    id="t_sug_risk",
                    name="suggest",
                    args={"ticker": "AAPL", "direction": "buy", "conviction": 0.8},
                ),
            ],
            outgoing_messages=[
                OutgoingMessage(to_agent="portfolio_manager", chat="AAPL", text="Rischio approvato per AAPL")
            ],
            done=True,
        ),
        ("technical_analyst", 0): StepResult(
            tool_calls=[
                ToolCall(
                    id="t_tech",
                    name="set_coefficients",
                    args={"ticker": "AAPL", "k_stop": 2.0, "k_tp": 3.5},
                ),
                ToolCall(
                    id="t_sug_tech",
                    name="suggest",
                    args={"ticker": "AAPL", "direction": "buy", "conviction": 0.85},
                ),
            ],
            outgoing_messages=[
                OutgoingMessage(to_agent="portfolio_manager", chat="AAPL", text="Setup tecnico pronto per AAPL")
            ],
            done=True,
        ),
        ("portfolio_manager", 1): StepResult(
            tool_calls=[
                ToolCall(
                    id="t_sched",
                    name="schedule_next_check",
                    args={"ticker": "AAPL", "when": "2026-06-05T10:00:00Z", "note": "Post-entry check"},
                ),
                ToolCall(
                    id="t_acc",
                    name="accept_order",
                    args={"ticker": "AAPL", "action": "buy", "reason": "Forte convergenza tecnica e di rischio"},
                ),
            ],
            done=True,
        ),
    }

    backend = ScriptedBackend(script)
    registry = RegistryWriter(db=db)

    office = Office(
        db=db,
        backend=backend,
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        registry=registry,
        sleep_fn=lambda _: None,
    )

    db.connection.execute(
        "INSERT INTO securities (symbol, name, sector) VALUES ('AAPL', 'Apple Inc.', 'Technology')"
    )

    task = ScheduledTask(
        agent="portfolio_manager",
        chat="AAPL",
        when=fixed_now,
        source=TaskSource.AGENT,
        reason="Triggering analysis cycle",
    )

    outcome = office.deliver(task)
    assert outcome == "accepted"

    # Verify Cycle closed with accepted outcome
    cycle_row = db.connection.execute(
        "SELECT * FROM cycles WHERE ticker = 'AAPL' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert cycle_row["outcome"] == "accepted"
    assert cycle_row["status"] == "closed"

    # Verify Broker received bracket order
    open_orders = broker.get_open_orders("AAPL")
    assert len(open_orders) == 1
    b_order = open_orders[0]
    assert b_order.symbol == "AAPL"
    assert b_order.side == "buy"
    assert b_order.limit_price > 0
    assert b_order.stop_loss is not None
    assert b_order.take_profit is not None

    # Verify Orders table in DB
    order_in_db = db.connection.execute(
        "SELECT * FROM orders WHERE ticker = 'AAPL'"
    ).fetchone()
    assert order_in_db is not None
    assert order_in_db["status"] == "submitted"

    # Verify mandatory future scheduled task exists in scheduled_tasks
    future_tasks = db.connection.execute(
        "SELECT * FROM scheduled_tasks WHERE chat = 'AAPL' AND status = 'pending'"
    ).fetchall()
    assert len(future_tasks) >= 1

    registry.close()


def test_risk_gate_rejection_leads_to_rimando_with_reasons_and_future_task(
    db, broker, env, order_flow, fixed_now
):
    """Stories 55, 61: When order is rejected by Risk Gate, message with reasons in PM chat + next trading day task."""
    # Pre-configure settings with tight risk limit that will trigger a block
    settings = OfficeSettings()
    settings.limits.max_risk_per_trade_fraction = 0.000001  # Too tight -> will fail Risk Gate

    script = {
        ("portfolio_manager", 0): StepResult(
            tool_calls=[
                ToolCall(
                    id="tc_sug",
                    name="suggest",
                    args={"ticker": "AAPL", "direction": "buy", "conviction": 0.9},
                ),
                ToolCall(
                    id="tc_sched",
                    name="schedule_next_check",
                    args={"ticker": "AAPL", "when": "2026-06-03T10:00:00Z"},
                ),
                ToolCall(
                    id="tc_acc",
                    name="accept_order",
                    args={"ticker": "AAPL", "action": "buy", "reason": "Try buying"},
                ),
            ],
            done=True,
        )
    }
    backend = ScriptedBackend(script)

    office = Office(
        db=db,
        backend=backend,
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        settings=settings,
        sleep_fn=lambda _: None,
    )

    task = ScheduledTask(
        agent="portfolio_manager",
        chat="AAPL",
        when=fixed_now,
        source=TaskSource.MANUAL,
        reason="Manual check",
    )

    outcome = office.deliver(task)
    assert outcome == "rimando"

    # Broker should NOT have received an order
    assert len(broker.get_open_orders()) == 0

    # PM chat contains Rimando message with reason
    pm_chat_id = db.get_or_create_chat("portfolio_manager", "AAPL")
    msgs = db.list_messages(pm_chat_id)
    rimando_msgs = [m for m in msgs if "Rimando:" in m["text"]]
    assert len(rimando_msgs) >= 1
    assert "Motivo:" in rimando_msgs[-1]["text"]

    # Verify future scheduled task exists
    future_tasks = db.connection.execute(
        "SELECT * FROM scheduled_tasks WHERE chat = 'AAPL' AND status = 'pending'"
    ).fetchall()
    assert len(future_tasks) >= 1


def test_budget_exhaustion_produces_deterministic_rimando_and_inbox_warning(
    db, broker, env, order_flow, fixed_now
):
    """Stories 30, 31: Cycle budget exhaustion triggers deterministic Rimando + Inbox warning + scheduled task."""
    settings = OfficeSettings(budgets=BudgetsConfig(cycle_budget=2))

    # Looping PM that keeps sending messages without deciding
    def infinite_loop(agent, chat_context, tools, turn):
        return StepResult(
            outgoing_messages=[
                OutgoingMessage(to_agent="risk_analyst", chat="AAPL", text=f"Message {turn}")
            ],
            done=False,
        )

    backend = ScriptedBackend(infinite_loop)

    office = Office(
        db=db,
        backend=backend,
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        settings=settings,
        sleep_fn=lambda _: None,
    )

    task = ScheduledTask(
        agent="portfolio_manager",
        chat="AAPL",
        when=fixed_now,
        source=TaskSource.AGENT,
        reason="Test loop",
    )

    outcome = office.deliver(task)
    assert outcome == "rimando"

    # Check inbox warning
    inbox = db.list_inbox()
    assert any(item["kind"] == "warning" and "Budget" in item["text"] for item in inbox)

    # Check cycle closed with rimando
    cycle = db.connection.execute(
        "SELECT * FROM cycles WHERE ticker = 'AAPL' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert cycle["outcome"] == "rimando"
    assert cycle["status"] == "closed"


def test_error_retry_analyst_error_continues_pm_failure_produces_rimando(
    db, broker, env, order_flow, fixed_now
):
    """Story 111, 112, 113: Transient error retried twice. Analyst failure writes to chat & continues; PM failure triggers Rimando + Inbox."""
    # Subtest 1: Specialist analyst fails 3 times -> writes error to chat, cycle continues
    script_analyst_failure = {
        ("portfolio_manager", 0): StepResult(
            outgoing_messages=[
                OutgoingMessage(to_agent="sentiment_analyst", chat="AAPL", text="Check sentiment")
            ],
            done=True,
        ),
        ("sentiment_analyst", 0): RuntimeError("API connection failure"),
        ("sentiment_analyst", 1): RuntimeError("API connection failure"),
        ("sentiment_analyst", 2): RuntimeError("API connection failure"),
        ("portfolio_manager", 1): StepResult(
            tool_calls=[
                ToolCall(
                    id="tc_sched",
                    name="schedule_next_check",
                    args={"ticker": "AAPL", "when": "2026-06-03T10:00:00Z"},
                ),
                ToolCall(
                    id="tc_def",
                    name="defer",
                    args={"ticker": "AAPL", "reason": "Analyst unavailable"},
                ),
            ],
            done=True,
        ),
    }

    backend1 = ScriptedBackend(script_analyst_failure)
    office1 = Office(
        db=db,
        backend=backend1,
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )

    task1 = ScheduledTask(
        agent="portfolio_manager",
        chat="AAPL",
        when=fixed_now,
        source=TaskSource.AGENT,
        reason="Analyst error test",
    )
    outcome1 = office1.deliver(task1)
    assert outcome1 == "deferred"

    # Check sentiment chat has the recorded error
    sent_chat_id = db.get_or_create_chat("sentiment_analyst", "AAPL")
    sent_msgs = db.list_messages(sent_chat_id)
    assert any("Errore" in m["text"] for m in sent_msgs)

    # Subtest 2: PM failure persistently -> Rimando + Inbox warning
    script_pm_failure = {
        ("portfolio_manager", 0): RuntimeError("PM LLM completely down"),
        ("portfolio_manager", 1): RuntimeError("PM LLM completely down"),
        ("portfolio_manager", 2): RuntimeError("PM LLM completely down"),
    }
    backend2 = ScriptedBackend(script_pm_failure)
    office2 = Office(
        db=db,
        backend=backend2,
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )

    task2 = ScheduledTask(
        agent="portfolio_manager",
        chat="MSFT",
        when=fixed_now,
        source=TaskSource.AGENT,
        reason="PM failure test",
    )
    outcome2 = office2.deliver(task2)
    assert outcome2 == "rimando"

    # Verify Inbox has error
    inbox = db.list_inbox()
    assert any(i["kind"] == "error" and "Fallimento PM" in i["text"] for i in inbox)


def test_market_analyst_activation_produces_scheduled_task_for_watchlist_ticker(
    db, broker, env, order_flow, fixed_now
):
    """Stories 76-80: Standalone Market Analyst message to PM produces scheduled task on watchlist ticker and opens cycle."""
    # Add AAPL to watchlist
    db.add_watchlist("AAPL", note="Key holding")

    script = {
        ("market_analyst", 0): StepResult(
            outgoing_messages=[
                OutgoingMessage(
                    to_agent="portfolio_manager",
                    chat="AAPL",
                    text="Catalizzatore: nuovo annuncio regolatorio favorevole per AAPL",
                )
            ],
            done=True,
        ),
        # When AAPL cycle opens as a result:
        ("portfolio_manager", 0): StepResult(
            tool_calls=[
                ToolCall(
                    id="tc_sched",
                    name="schedule_next_check",
                    args={"ticker": "AAPL", "when": "2026-06-03T10:00:00Z"},
                ),
                ToolCall(
                    id="tc_def",
                    name="defer",
                    args={"ticker": "AAPL", "reason": "Catalyst assessed, defer to next session"},
                ),
            ],
            done=True,
        ),
    }

    backend = ScriptedBackend(script)
    office = Office(
        db=db,
        backend=backend,
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )

    market_task = ScheduledTask(
        agent="market_analyst",
        chat="tech_macro",
        when=fixed_now,
        source=TaskSource.ALERT_CALENDAR,
        reason="Scheduled macro review",
    )

    res = office.deliver(market_task)
    assert res == "market_analyst_activated"

    # Verify that scheduled task with source=market_message was created in DB
    market_tasks = db.connection.execute(
        "SELECT * FROM scheduled_tasks WHERE source = 'market_message'"
    ).fetchall()
    assert len(market_tasks) == 1
    assert market_tasks[0]["chat"] == "AAPL"

    # Verify cycle was opened for AAPL
    cycle = db.connection.execute(
        "SELECT * FROM cycles WHERE ticker = 'AAPL'"
    ).fetchone()
    assert cycle is not None
    assert cycle["outcome"] == "deferred"


def test_market_analyst_send_message_tool_call_activates_watchlist_ticker(
    db, broker, env, order_flow, fixed_now
):
    """A send_message tool call from the Market Analyst (not a plain outgoing message) activates the PM."""
    # Add AAPL to watchlist
    db.add_watchlist("AAPL", note="Key holding")

    script = {
        ("market_analyst", 0): StepResult(
            tool_calls=[
                ToolCall(
                    id="tc_msg",
                    name="send_message",
                    args={
                        "to_agent": "portfolio_manager",
                        "ticker_or_theme": "AAPL",
                        "text": "Catalizzatore: nuovo annuncio regolatorio favorevole per AAPL",
                    },
                )
            ],
            done=True,
        ),
        # When AAPL cycle opens as a result:
        ("portfolio_manager", 0): StepResult(
            tool_calls=[
                ToolCall(
                    id="tc_sched",
                    name="schedule_next_check",
                    args={"ticker": "AAPL", "when": "2026-06-03T10:00:00Z"},
                ),
                ToolCall(
                    id="tc_def",
                    name="defer",
                    args={"ticker": "AAPL", "reason": "Catalyst assessed, defer to next session"},
                ),
            ],
            done=True,
        ),
    }

    backend = ScriptedBackend(script)
    office = Office(
        db=db,
        backend=backend,
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )

    market_task = ScheduledTask(
        agent="market_analyst",
        chat="tech_macro",
        when=fixed_now,
        source=TaskSource.ALERT_CALENDAR,
        reason="Scheduled macro review",
    )

    res = office.deliver(market_task)
    assert res == "market_analyst_activated"

    # Verify that scheduled task with source=market_message was created in DB
    market_tasks = db.connection.execute(
        "SELECT * FROM scheduled_tasks WHERE source = 'market_message'"
    ).fetchall()
    assert len(market_tasks) == 1
    assert market_tasks[0]["chat"] == "AAPL"

    # Verify cycle was opened for AAPL
    cycle = db.connection.execute(
        "SELECT * FROM cycles WHERE ticker = 'AAPL'"
    ).fetchone()
    assert cycle is not None
    assert cycle["outcome"] == "deferred"


def test_halt_stops_delivery(db, broker, env, order_flow, fixed_now):
    """Story 114: Halt stops delivery immediately."""
    halt = SystemHalt(db, broker)
    halt.halt()
    assert halt.is_halted()

    office = Office(
        db=db,
        backend=ScriptedBackend({}),
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )

    task = ScheduledTask(
        agent="portfolio_manager",
        chat="AAPL",
        when=fixed_now,
        source=TaskSource.AGENT,
        reason="Should be stopped",
    )

    res = office.deliver(task)
    assert res is None

    # No cycle opened
    cycles = db.connection.execute("SELECT * FROM cycles").fetchall()
    assert len(cycles) == 0


def test_run_once_merges_tasks_delivers_and_advances_cursor(
    db, broker, env, order_flow, fixed_now
):
    """Test scheduler loop run_once: merges same-chat tasks, delivers due tasks, and advances cursor."""
    # Enqueue two tasks for same ticker AAPL at different times
    t1_iso = fixed_now.isoformat().replace("+00:00", "Z")
    t2_iso = (fixed_now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")

    id1 = db.enqueue_scheduled_task(
        agent="portfolio_manager",
        chat="AAPL",
        when_ts=t1_iso,
        source="agent",
        reason="Weekly check 1",
    )
    id2 = db.enqueue_scheduled_task(
        agent="portfolio_manager",
        chat="AAPL",
        when_ts=t2_iso,
        source="alert_price",
        reason="Price alert 2",
    )

    script = {
        ("portfolio_manager", 0): StepResult(
            tool_calls=[
                ToolCall(
                    id="tc_sched",
                    name="schedule_next_check",
                    args={"ticker": "AAPL", "when": "2026-06-03T10:00:00Z"},
                ),
                ToolCall(
                    id="tc_def",
                    name="defer",
                    args={"ticker": "AAPL", "reason": "Merged tasks evaluated"},
                ),
            ],
            done=True,
        )
    }

    backend = ScriptedBackend(script)
    office = Office(
        db=db,
        backend=backend,
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now + timedelta(minutes=5),
        sleep_fn=lambda _: None,
    )

    outcomes = office.run_once(now=fixed_now + timedelta(minutes=5))
    assert len(outcomes) == 1
    assert outcomes[0] == "deferred"

    # Task id2 should be marked as merged into id1
    t2_row = db.get_scheduled_task(id2)
    assert t2_row["status"] == "merged"
    assert t2_row["merged_into"] == id1

    # Task id1 should be marked as delivered
    t1_row = db.get_scheduled_task(id1)
    assert t1_row["status"] == "delivered"

    # Second run_once with same time should deliver nothing (cursor advanced)
    second_outcomes = office.run_once(now=fixed_now + timedelta(minutes=5))
    assert len(second_outcomes) == 0


def test_pm_sees_tool_results_on_next_step_within_same_turn(db, broker, env, order_flow, fixed_now):
    """Regressione: il PM legge uno strumento, riceve il risultato e decide nello stesso ciclo."""
    seen_tool_messages: list[ChatMessage] = []

    def script(agent, chat_context, tools, turn):
        if agent.name != "portfolio_manager":
            return StepResult(done=True)
        if turn == 0:
            return StepResult(
                tool_calls=[ToolCall(id="r1", name="read_state", args={"ticker": "AAPL"})],
                done=False,
            )
        seen_tool_messages.extend(m for m in chat_context if m.role == "tool")
        return StepResult(
            tool_calls=[
                ToolCall(
                    id="s1",
                    name="schedule_next_check",
                    args={"ticker": "AAPL", "when": "2026-06-05T10:00:00Z", "note": "ricontrollo"},
                ),
                ToolCall(id="d1", name="defer", args={"ticker": "AAPL", "reason": "nessun setup"}),
            ],
            done=True,
        )

    office = Office(
        db=db,
        backend=ScriptedBackend(script),
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        registry=RegistryWriter(db=db),
        sleep_fn=lambda _: None,
    )
    outcome = office.deliver(
        ScheduledTask(
            agent="portfolio_manager",
            chat="AAPL",
            when=fixed_now,
            source=TaskSource.MANUAL,
            reason="test loop",
        )
    )
    assert outcome == "deferred"
    assert seen_tool_messages, "il PM non ha ricevuto il risultato dello strumento"
    assert seen_tool_messages[0].tool_call_id == "r1"


def test_pm_cannot_decide_in_same_step_it_consults_analysts(
    db, broker, env, order_flow, fixed_now
):
    """Il PM scrive all'analista e prova a rimandare subito: la decisione viene rifiutata,
    l'analista risponde, il PM decide al turno dopo."""
    analyst_turns = {"n": 0}

    def script(agent, chat_context, tools, turn):
        if agent.name == "risk_analyst":
            analyst_turns["n"] += 1
            return StepResult(
                outgoing_messages=[
                    OutgoingMessage(to_agent="portfolio_manager", chat="AAPL", text="Rischio ok")
                ],
                done=True,
            )
        if turn == 0:
            return StepResult(
                tool_calls=[
                    ToolCall(
                        id="m1",
                        name="send_message",
                        args={"to_agent": "risk_analyst", "ticker_or_theme": "AAPL", "text": "Valuta"},
                    ),
                    ToolCall(
                        id="s1",
                        name="schedule_next_check",
                        args={"ticker": "AAPL", "when": "2026-06-05T10:00:00Z", "note": "n"},
                    ),
                    ToolCall(id="d1", name="defer", args={"ticker": "AAPL", "reason": "presto"}),
                ],
                done=True,
            )
        return StepResult(
            tool_calls=[ToolCall(id="d2", name="defer", args={"ticker": "AAPL", "reason": "ok"})],
            done=True,
        )

    office = Office(
        db=db,
        backend=ScriptedBackend(script),
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        registry=RegistryWriter(db=db),
        sleep_fn=lambda _: None,
    )
    outcome = office.deliver(
        ScheduledTask(
            agent="portfolio_manager",
            chat="AAPL",
            when=fixed_now,
            source=TaskSource.MANUAL,
            reason="test guardia",
        )
    )
    assert analyst_turns["n"] >= 1, "l'analista non ha avuto il suo turno"
    assert outcome == "deferred"
    errs = db.connection.execute(
        "SELECT COUNT(*) AS c FROM tool_calls WHERE tool = 'defer'"
    ).fetchone()["c"]
    assert errs == 1, "il primo defer doveva essere rifiutato"


def test_new_cycle_does_not_inherit_previous_decision(db, broker, env, order_flow, fixed_now):
    """Regressione in produzione: il secondo ciclo si chiudeva subito con la decisione del primo."""

    def script(agent, chat_context, tools, turn):
        return StepResult(
            tool_calls=[
                ToolCall(
                    id=f"s{turn}",
                    name="schedule_next_check",
                    args={"ticker": "AAPL", "when": "2026-06-05T10:00:00Z", "note": "n"},
                ),
                ToolCall(id=f"d{turn}", name="defer", args={"ticker": "AAPL", "reason": f"c{turn}"}),
            ],
            done=True,
        )

    backend = ScriptedBackend(script)
    office = Office(
        db=db,
        backend=backend,
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        registry=RegistryWriter(db=db),
        sleep_fn=lambda _: None,
    )
    for i in range(2):
        office.deliver(
            ScheduledTask(
                agent="portfolio_manager",
                chat="AAPL",
                when=fixed_now + timedelta(hours=i),
                source=TaskSource.MANUAL,
                reason=f"ciclo {i}",
            )
        )
    assert len([c for c in backend.calls if c.agent.name == "portfolio_manager"]) >= 2
    reasons = [
        json.loads(r["params_json"])["reason"]
        for r in db.connection.execute("SELECT params_json FROM tool_calls WHERE tool = 'defer'")
    ]
    assert reasons == ["c0", "c1"]


def test_analyst_reply_is_relayed_to_pm_when_not_addressed(db, broker, env, order_flow, fixed_now):
    """Produzione: gli analisti rispondevano in chat propria o al market analyst e il PM non
    riceveva nulla. La risposta finale arriva comunque al PM, che poi decide."""

    def script(agent, chat_context, tools, turn):
        if agent.name == "risk_analyst":
            return StepResult(content="Rischio ok, size piccola", done=True)
        if turn == 0:
            return StepResult(
                tool_calls=[
                    ToolCall(
                        id="m1",
                        name="send_message",
                        args={"to_agent": "risk_analyst", "ticker_or_theme": "AAPL", "text": "Valuta"},
                    )
                ],
                done=True,
            )
        assert any("Rischio ok" in m.content for m in chat_context), "il PM non vede la risposta"
        return StepResult(
            tool_calls=[
                ToolCall(
                    id="s1",
                    name="schedule_next_check",
                    args={"ticker": "AAPL", "when": "2026-06-05T10:00:00Z", "note": "n"},
                ),
                ToolCall(id="d1", name="defer", args={"ticker": "AAPL", "reason": "ok"}),
            ],
            done=True,
        )

    office = Office(
        db=db,
        backend=ScriptedBackend(script),
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        registry=RegistryWriter(db=db),
        sleep_fn=lambda _: None,
    )
    outcome = office.deliver(
        ScheduledTask(
            agent="portfolio_manager",
            chat="AAPL",
            when=fixed_now,
            source=TaskSource.MANUAL,
            reason="relay",
        )
    )
    assert outcome == "deferred"


def test_stored_legacy_draft_prices_are_rounded_to_cents():
    from decimal import Decimal

    from workflows.cycle import _cents

    assert _cents(350.03732650705064) == Decimal("350.04")
    assert _cents("338.505") == Decimal("338.51")


def test_office_db_size_alert_inbox(db, broker, env, order_flow, fixed_now):
    """Stories 102, 117: Office checks db size on run_once and records inbox alert."""
    settings = OfficeSettings(db_size_alert_mb=1)
    office = Office(
        db=db,
        backend=ScriptedBackend({}),
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        settings=settings,
        sleep_fn=lambda _: None,
    )
    # Under limit
    office.run_once()
    assert len(db.list_inbox(unread_only=True)) == 0

    # Exceed limit
    dummy = "x" * (1024 * 1024 + 500)
    db.connection.execute("INSERT INTO blobs (hash, compressed) VALUES ('big_blob', ?)", (dummy.encode(),))
    office.run_once()

    inbox = db.list_inbox(unread_only=True)
    assert any(i["kind"] == "db_size" and "Allarme dimensione DB" in i["text"] for i in inbox)


def test_office_run_retention(db, broker, env, order_flow, fixed_now):
    """Story 101: Office runs retention job."""
    office = Office(
        db=db,
        backend=ScriptedBackend({}),
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )
    res = office.run_retention()
    assert isinstance(res, dict)
    assert "compacted_news" in res
    assert "downsampled_hourly" in res


def test_office_periodic_data_refresh(db, broker, env, order_flow, fixed_now):
    """Story 89: Pre-fetch watchlist and portfolio data periodically."""
    from data.cache import DataCache

    db.add_watchlist("AAPL")
    cache = DataCache(db=db, providers={"prices_ohlcv": lambda s, **kw: [{"symbol": s, "ts": "2026-11-18T10:00:00Z", "interval": "1d", "o": 100.0, "h": 105.0, "l": 99.0, "c": 104.0, "v": 1000.0, "source": "test"}]})

    office = Office(
        db=db,
        backend=ScriptedBackend({}),
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )
    office.data_cache = cache
    report = office.refresh_data()
    assert report is not None
    assert "AAPL" in report["tickers"]
    assert report["refreshed"] >= 1


def test_office_ingest_external_alert(db, broker, env, order_flow, fixed_now):
    """Story 12: Ingest external alert transforms to immediate scheduled task and delivers."""
    office = Office(
        db=db,
        backend=ScriptedBackend({}),
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )
    task_id = office.ingest_external_alert(
        alert_type="price",
        ticker="AAPL",
        reason="Breakout above 180",
        data={"price": 182.5},
    )
    assert task_id > 0

    task_row = db.get_scheduled_task(task_id)
    assert task_row["agent"] == "portfolio_manager"
    assert task_row["chat"] == "AAPL"
    assert task_row["source"] == "alert_price"
    assert "Breakout above 180" in task_row["reason"]


def test_office_fixed_market_analyst_activations(db, broker, env, order_flow, fixed_now):
    """Story 16: Fixed activations for Market Analyst (pre-market and macro events)."""
    # fixed_now is 2026-06-02 (Tuesday, trading day)
    office = Office(
        db=db,
        backend=ScriptedBackend({}),
        env_factory=env,
        order_flow=order_flow,
        clock=lambda: fixed_now,
        sleep_fn=lambda _: None,
    )

    # Insert an upcoming econ calendar event
    evt_ts = (fixed_now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    db.connection.execute(
        """
        INSERT INTO econ_calendar (event_id, event_name, event_ts, impact, source, fetched_at)
        VALUES ('fomc-1', 'FOMC Rate Decision', ?, 'high', 'test', '2026-06-02')
        """,
        (evt_ts,),
    )

    created_ids = office.ensure_fixed_market_analyst_activations(fixed_now)
    assert len(created_ids) == 2  # 1 pre-market + 1 econ calendar

    tasks = db.connection.execute(
        "SELECT * FROM scheduled_tasks WHERE agent = 'market_analyst' AND source = 'fixed_base'"
    ).fetchall()
    assert len(tasks) == 2

    # Check pre-market task
    premkt = next(t for t in tasks if t["data_json"] and '"pre_market"' in t["data_json"])
    assert "pre-market" in premkt["reason"]
    assert premkt["chat"] == "Macro"

    # Check econ calendar task
    macro_evt = next(t for t in tasks if t["data_json"] and '"fomc-1"' in t["data_json"])
    assert "FOMC Rate Decision" in macro_evt["reason"]

    # Calling again does not duplicate tasks
    second_run = office.ensure_fixed_market_analyst_activations(fixed_now)
    assert len(second_run) == 0
