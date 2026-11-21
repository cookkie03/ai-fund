"""Tests for AgentEnvironment and tool execution."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from agents.backend import ToolCall
from brokers.models import Account, Position
from storage.office_db import OfficeDB
from tools.environment import AgentEnvironment, BrokerReader, MarketData


class FakeMarketData:
    """In-memory market data implementing MarketData protocol."""

    def __init__(self) -> None:
        self._quotes = {
            "AAPL": {"symbol": "AAPL", "price": 150.0, "atr": 2.5},
            "MSFT": {"symbol": "MSFT", "price": 300.0, "atr": 4.0},
        }

    def quote(self, symbol: str) -> dict[str, Any]:
        return self._quotes.get(symbol, {"symbol": symbol, "price": 100.0, "atr": 2.0})

    def ohlcv(
        self, symbol: str, interval: str = "1d", limit: int = 100
    ) -> list[dict[str, Any]]:
        # Return 30 bars with rising prices
        bars = []
        base = 100.0
        for i in range(35):
            o = base + i
            h = o + 2.0
            low = o - 1.5
            c = o + 1.0
            bars.append({"ts": f"2026-01-{i+1:02d}T00:00:00Z", "o": o, "h": h, "l": low, "c": c, "v": 1000})
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


class FakeBroker:
    """In-memory broker reader implementing BrokerReader protocol."""

    def __init__(self, equity: Decimal = Decimal("100000"), cash: Decimal = Decimal("50000")) -> None:
        self.account = Account(
            id="test-acc",
            status="ACTIVE",
            currency="USD",
            cash=cash,
            equity=equity,
            buying_power=cash * Decimal("2"),
            trading_blocked=False,
        )
        self.positions: list[Position] = [
            Position(
                symbol="AAPL",
                asset_class="us_equity",
                side="long",
                quantity=Decimal("50"),
                quantity_available=Decimal("50"),
                average_entry_price=Decimal("140.0"),
                current_price=Decimal("150.0"),
                market_value=Decimal("7500.0"),
                unrealized_profit_loss=Decimal("500.0"),
            )
        ]
        self.orders: list[Any] = []

    def get_account(self) -> Account:
        return self.account

    def get_positions(self) -> list[Position]:
        return self.positions

    def get_orders(self, query: Any = None) -> list[Any]:
        return self.orders


@pytest.fixture
def test_setup(tmp_path):
    db_file = tmp_path / "office_test.db"
    db = OfficeDB(db_file)
    # Populate a security for sector lookup
    db.connection.execute(
        "INSERT INTO securities (symbol, name, sector, industry) VALUES (?, ?, ?, ?)",
        ("AAPL", "Apple Inc", "Technology", "Consumer Electronics"),
    )

    market_data = FakeMarketData()
    broker = FakeBroker()
    fixed_now = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)

    logs: list[tuple] = []

    def test_logger(agent, chat_id, tool, params, result, error):
        logs.append((agent, chat_id, tool, params, result, error))

    accepted_intents: list[tuple[str, str, str]] = []

    def test_on_accept(ticker, action, reason):
        accepted_intents.append((ticker, action, reason))

    subagent_tasks: list[str] = []

    def test_subagent_caller(task: str) -> str:
        subagent_tasks.append(task)
        return f"Done: {task}"

    env = AgentEnvironment(
        db=db,
        market_data=market_data,
        broker_reader=broker,
        now=fixed_now,
        logger=test_logger,
        subagent_caller=test_subagent_caller,
        on_accept=test_on_accept,
    )

    return {
        "db": db,
        "market_data": market_data,
        "broker": broker,
        "env": env,
        "logs": logs,
        "accepted_intents": accepted_intents,
        "subagent_tasks": subagent_tasks,
        "now": fixed_now,
    }


def _get_tool_map(tools):
    return {t.name: t for t in tools}


# -----------------------------------------------------------------------------
# 1. Protocols & Universal Tools
# -----------------------------------------------------------------------------


def test_protocols_conformance(test_setup):
    assert isinstance(test_setup["market_data"], MarketData)
    assert isinstance(test_setup["broker"], BrokerReader)


def test_read_state_and_portfolio(test_setup):
    env: AgentEnvironment = test_setup["env"]
    tools = _get_tool_map(env.tools_for("technical_analyst", chat_id=1))

    # Read empty state
    res_state = tools["read_state"].execute(ToolCall(id="1", name="read_state", args={"ticker": "AAPL"}))
    assert res_state["ticker"] == "AAPL"

    # Read portfolio
    res_port = tools["read_portfolio"].execute(ToolCall(id="2", name="read_portfolio", args={}))
    assert res_port["account"]["equity"] == 100000.0
    assert len(res_port["positions"]) == 1
    assert res_port["positions"][0]["symbol"] == "AAPL"


def test_send_message_sector_delivery_and_db(test_setup):
    env: AgentEnvironment = test_setup["env"]
    db: OfficeDB = test_setup["db"]
    tools = _get_tool_map(env.tools_for("technical_analyst", chat_id=1))

    # Send message to market_analyst on AAPL -> must deliver to 'Technology' sector chat
    res = tools["send_message"].execute(
        ToolCall(
            id="1",
            name="send_message",
            args={
                "to_agent": "market_analyst",
                "ticker_or_theme": "AAPL",
                "text": "What is the tech macro outlook?",
            },
        )
    )
    assert res["status"] == "delivered"
    assert res["topic"] == "Technology"

    # Verify message in DB
    chat = db.get_chat(res["chat_id"])
    assert chat["agent"] == "market_analyst"
    assert chat["topic"] == "Technology"
    msgs = db.list_messages(res["chat_id"])
    assert len(msgs) == 1
    assert msgs[0]["author"] == "technical_analyst"
    assert msgs[0]["text"] == "What is the tech macro outlook?"


def test_call_subagent_and_budget(test_setup):
    env: AgentEnvironment = test_setup["env"]
    db: OfficeDB = test_setup["db"]

    cycle_id = db.open_cycle(ticker="AAPL")
    tools = _get_tool_map(env.tools_for("sentiment_analyst", chat_id=1, cycle_id=cycle_id))

    res = tools["call_subagent"].execute(
        ToolCall(id="1", name="call_subagent", args={"task": "Find sentiment on AAPL"})
    )
    assert "Done: Find sentiment on AAPL" in res["result"]
    assert test_setup["subagent_tasks"] == ["Find sentiment on AAPL"]

    # Verify budget updated in cycle
    cycle = db.get_cycle(cycle_id)
    budget = json.loads(cycle["budget_used_json"])
    assert budget["subagents"] == 1


def test_subagent_restrictions(test_setup):
    env: AgentEnvironment = test_setup["env"]
    tools = _get_tool_map(env.tools_for("subagent", chat_id=1))

    # Subagents must never have send_message or call_subagent
    assert "send_message" not in tools
    assert "call_subagent" not in tools
    assert "accept_order" not in tools


# -----------------------------------------------------------------------------
# 2. Analyst Analysis, Suggestions, Coefficients, and Draft Recomputation
# -----------------------------------------------------------------------------


def test_analyst_write_analysis_and_suggest(test_setup):
    env: AgentEnvironment = test_setup["env"]
    db: OfficeDB = test_setup["db"]
    tools = _get_tool_map(env.tools_for("technical_analyst", chat_id=1))

    # Write analysis
    tools["write_analysis"].execute(
        ToolCall(
            id="1",
            name="write_analysis",
            args={"ticker": "AAPL", "section_text": "Strong uptrend above SMA20."},
        )
    )
    state = json.loads(db.get_ticker_state("AAPL")["state_json"])
    assert state["analyses"]["technical_analyst"] == "Strong uptrend above SMA20."

    # Suggest direction
    tools["suggest"].execute(
        ToolCall(
            id="2",
            name="suggest",
            args={"ticker": "AAPL", "direction": "buy", "conviction": 0.8},
        )
    )
    state = json.loads(db.get_ticker_state("AAPL")["state_json"])
    assert state["suggestions"]["technical_analyst"] == {"direction": "buy", "conviction": 0.8}

    # Invalid suggestion direction
    with pytest.raises(ValueError):
        tools["suggest"].execute(
            ToolCall(
                id="3",
                name="suggest",
                args={"ticker": "AAPL", "direction": "fly", "conviction": 0.5},
            )
        )

    # Invalid conviction
    with pytest.raises(ValueError):
        tools["suggest"].execute(
            ToolCall(
                id="4",
                name="suggest",
                args={"ticker": "AAPL", "direction": "buy", "conviction": 1.5},
            )
        )


def test_coefficients_role_permissions_and_bounds(test_setup):
    env: AgentEnvironment = test_setup["env"]
    db: OfficeDB = test_setup["db"]

    risk_tools = _get_tool_map(env.tools_for("risk_analyst", chat_id=1))
    tech_tools = _get_tool_map(env.tools_for("technical_analyst", chat_id=1))
    sent_tools = _get_tool_map(env.tools_for("sentiment_analyst", chat_id=1))

    # 1. Risk analyst setting k_entry and risk_fraction: allowed
    risk_tools["set_coefficients"].execute(
        ToolCall(
            id="1",
            name="set_coefficients",
            args={"ticker": "AAPL", "k_entry": 0.5, "risk_fraction": 0.01},
        )
    )
    state = json.loads(db.get_ticker_state("AAPL")["state_json"])
    assert state["coefficients"]["k_entry"] == 0.5
    assert state["coefficients"]["risk_fraction"] == 0.01

    # Risk analyst trying to set k_stop: rejected
    with pytest.raises(ValueError, match="risk_analyst may only set k_entry"):
        risk_tools["set_coefficients"].execute(
            ToolCall(
                id="2",
                name="set_coefficients",
                args={"ticker": "AAPL", "k_stop": 2.5},
            )
        )

    # 2. Technical analyst setting k_stop, k_tp, k_trail_act, k_trail: allowed
    tech_tools["set_coefficients"].execute(
        ToolCall(
            id="3",
            name="set_coefficients",
            args={
                "ticker": "AAPL",
                "k_stop": 2.0,
                "k_tp": 3.5,
                "k_trail_act": 1.5,
                "k_trail": 1.0,
            },
        )
    )
    state = json.loads(db.get_ticker_state("AAPL")["state_json"])
    assert state["coefficients"]["k_stop"] == 2.0
    assert state["coefficients"]["k_tp"] == 3.5

    # Technical analyst trying to set k_entry: rejected
    with pytest.raises(ValueError, match="technical_analyst may only set"):
        tech_tools["set_coefficients"].execute(
            ToolCall(
                id="4",
                name="set_coefficients",
                args={"ticker": "AAPL", "k_entry": 0.2},
            )
        )

    # 3. Sentiment analyst trying to set coefficients: rejected
    with pytest.raises(ValueError, match="not authorized to set coefficients"):
        sent_tools["set_coefficients"].execute(
            ToolCall(
                id="5",
                name="set_coefficients",
                args={"ticker": "AAPL", "k_stop": 2.0},
            )
        )

    # 4. Out of range values rejected
    with pytest.raises(ValueError, match="out of bounds"):
        risk_tools["set_coefficients"].execute(
            ToolCall(
                id="6",
                name="set_coefficients",
                args={"ticker": "AAPL", "risk_fraction": -0.05},
            )
        )


def test_order_draft_recomputed_after_changes(test_setup):
    env: AgentEnvironment = test_setup["env"]
    db: OfficeDB = test_setup["db"]

    tech_tools = _get_tool_map(env.tools_for("technical_analyst", chat_id=1))
    risk_tools = _get_tool_map(env.tools_for("risk_analyst", chat_id=1))

    # Give suggestion
    tech_tools["suggest"].execute(
        ToolCall(
            id="1",
            name="suggest",
            args={"ticker": "AAPL", "direction": "buy", "conviction": 0.8},
        )
    )
    # Set risk coeffs
    risk_tools["set_coefficients"].execute(
        ToolCall(
            id="2",
            name="set_coefficients",
            args={"ticker": "AAPL", "k_entry": 0.3, "risk_fraction": 0.01},
        )
    )

    state = json.loads(db.get_ticker_state("AAPL")["state_json"])
    # Draft must be populated
    draft = state.get("draft")
    assert draft is not None
    assert draft["symbol"] == "AAPL"
    assert draft["side"] == "buy"
    assert draft["quantity"] > 0
    assert draft["entry"] > 0
    assert draft["stop"] < draft["entry"]
    assert draft["take_profit"] > draft["entry"]
    assert "draft_hash" in draft


# -----------------------------------------------------------------------------
# 3. Role-specific Data Tools
# -----------------------------------------------------------------------------


def test_market_analyst_tools(test_setup):
    env: AgentEnvironment = test_setup["env"]
    db: OfficeDB = test_setup["db"]
    tools = _get_tool_map(env.tools_for("market_analyst", chat_id=1))

    # Macro, News by theme, Econ calendar, Sector perf
    macro_res = tools["macro"].execute(ToolCall(id="1", name="macro", args={"series_id": "CPI"}))
    assert macro_res[0]["series_id"] == "CPI"

    news_res = tools["news_by_theme"].execute(
        ToolCall(id="2", name="news_by_theme", args={"theme": "technology"})
    )
    assert len(news_res) > 0

    cal_res = tools["econ_calendar"].execute(ToolCall(id="3", name="econ_calendar", args={}))
    assert len(cal_res) > 0

    sec_res = tools["sector_perf"].execute(ToolCall(id="4", name="sector_perf", args={}))
    assert len(sec_res) > 0

    # Schedule task clamped
    target_dt = test_setup["now"] + timedelta(days=2)
    sched_res = tools["schedule_task"].execute(
        ToolCall(
            id="5",
            name="schedule_task",
            args={"chat": "Technology", "when": target_dt.isoformat(), "reason": "CPI release review"},
        )
    )
    assert sched_res["status"] == "scheduled"
    task = db.get_scheduled_task(sched_res["task_id"])
    assert task["agent"] == "market_analyst"
    assert task["chat"] == "Technology"

    # Story 77: set_sector_view updates sector_performance and ticker_state
    db.connection.execute(
        "INSERT OR REPLACE INTO securities (symbol, name, sector) VALUES ('AAPL', 'Apple', 'Technology')"
    )
    sv_res = tools["set_sector_view"].execute(
        ToolCall(
            id="6",
            name="set_sector_view",
            args={"sector": "Technology", "view": "Semiconductor demand robust"},
        )
    )
    assert sv_res["status"] == "updated"
    assert sv_res["sector"] == "Technology"
    assert "AAPL" in sv_res["tickers"]

    aapl_st = json.loads(db.get_ticker_state("AAPL")["state_json"])
    assert aapl_st["sector_view"] == "Semiconductor demand robust"


def test_sentiment_analyst_tools(test_setup):
    env: AgentEnvironment = test_setup["env"]
    tools = _get_tool_map(env.tools_for("sentiment_analyst", chat_id=1))

    news = tools["news_by_ticker"].execute(
        ToolCall(id="1", name="news_by_ticker", args={"ticker": "AAPL"})
    )
    assert len(news) > 0

    ratings = tools["ratings"].execute(ToolCall(id="2", name="ratings", args={"ticker": "AAPL"}))
    assert len(ratings) > 0

    insiders = tools["insiders"].execute(
        ToolCall(id="3", name="insiders", args={"ticker": "AAPL"})
    )
    assert len(insiders) > 0


def test_technical_analyst_indicators(test_setup):
    env: AgentEnvironment = test_setup["env"]
    tools = _get_tool_map(env.tools_for("technical_analyst", chat_id=1))

    res = tools["indicators"].execute(ToolCall(id="1", name="indicators", args={"ticker": "AAPL"}))
    assert res["ticker"] == "AAPL"
    assert "sma20" in res and res["sma20"] is not None
    assert "ema20" in res and res["ema20"] is not None
    assert "rsi14" in res and res["rsi14"] is not None
    assert "atr14" in res and res["atr14"] is not None
    assert "pivot" in res and res["pivot"]["pivot"] is not None


def test_agent_market_tools_follow_office_timeframe(tmp_path):
    from bootstrap import build_test_office
    from config.office_settings import OfficeSettings
    from storage.office_db import OfficeDB

    settings = OfficeSettings(market={"bar_timeframe": "5m"})
    office = build_test_office(db=OfficeDB(tmp_path / "office.db"), settings=settings)
    env = office.get_env()
    calls = []
    original = env.market_data.ohlcv

    def record(symbol, interval="1d", limit=100):
        calls.append(interval)
        return original(symbol, interval=interval, limit=limit)

    env.market_data.ohlcv = record
    tools = _get_tool_map(env.tools_for("technical_analyst", chat_id=1))
    tools["ohlcv"].execute(ToolCall(id="1", name="ohlcv", args={"ticker": "AAPL"}))
    tools["indicators"].execute(ToolCall(id="2", name="indicators", args={"ticker": "AAPL"}))
    tools["ohlcv"].execute(ToolCall(id="3", name="ohlcv", args={"ticker": "AAPL", "interval": "1d"}))
    assert calls == ["5m", "5m", "1d"]


def test_fundamental_analyst_tools(test_setup):
    env: AgentEnvironment = test_setup["env"]
    tools = _get_tool_map(env.tools_for("fundamental_analyst", chat_id=1))

    fin = tools["financials"].execute(ToolCall(id="1", name="financials", args={"ticker": "AAPL"}))
    assert fin["revenue"] == 1000000

    ratios = tools["ratios"].execute(ToolCall(id="2", name="ratios", args={"ticker": "AAPL"}))
    assert "pe" in ratios

    earnings = tools["earnings_dates"].execute(
        ToolCall(id="3", name="earnings_dates", args={"ticker": "AAPL"})
    )
    assert len(earnings) > 0


def test_risk_analyst_portfolio_risk(test_setup):
    env: AgentEnvironment = test_setup["env"]
    tools = _get_tool_map(env.tools_for("risk_analyst", chat_id=1))

    risk = tools["portfolio_risk"].execute(ToolCall(id="1", name="portfolio_risk", args={}))
    assert risk["equity"] == 100000.0
    assert risk["cash"] == 50000.0
    assert risk["open_positions_count"] == 1
    assert "Technology" in risk["sector_exposures"]
    assert "open_risk" in risk
    # Story 85: Correlation matrix computed for portfolio
    assert "correlations" in risk
    assert risk["correlations"]["AAPL"]["AAPL"] == 1.0


# -----------------------------------------------------------------------------
# 4. PM Tools: Decisions, Next Check Requirement, Watchlist
# -----------------------------------------------------------------------------


def test_pm_decision_requires_scheduled_check(test_setup):
    env: AgentEnvironment = test_setup["env"]
    db: OfficeDB = test_setup["db"]
    tools = _get_tool_map(env.tools_for("pm", chat_id=1))

    # Accept without future scheduled task must fail
    with pytest.raises(ValueError, match="requires a future scheduled task"):
        tools["accept_order"].execute(
            ToolCall(
                id="1",
                name="accept_order",
                args={"ticker": "AAPL", "action": "buy", "reason": "Valuation attractive"},
            )
        )

    # Defer without future scheduled task must fail
    with pytest.raises(ValueError, match="requires a future scheduled task"):
        tools["defer"].execute(
            ToolCall(
                id="2",
                name="defer",
                args={"ticker": "AAPL", "reason": "Need more data"},
            )
        )

    # Schedule next check
    future_time = test_setup["now"] + timedelta(days=5)
    tools["schedule_next_check"].execute(
        ToolCall(
            id="3",
            name="schedule_next_check",
            args={"ticker": "AAPL", "when": future_time.isoformat(), "note": "Re-evaluate post earnings"},
        )
    )

    # Now accept_order should succeed
    res = tools["accept_order"].execute(
        ToolCall(
            id="4",
            name="accept_order",
            args={"ticker": "AAPL", "action": "buy", "reason": "Valuation attractive"},
        )
    )
    assert res["status"] == "accepted"
    assert test_setup["accepted_intents"] == [("AAPL", "buy", "Valuation attractive")]

    # Check state updated
    state = json.loads(db.get_ticker_state("AAPL")["state_json"])
    assert state["decision"]["action"] == "buy"
    assert state["decision"]["reason"] == "Valuation attractive"


def test_pm_sell_requires_open_position(test_setup):
    env: AgentEnvironment = test_setup["env"]
    tools = _get_tool_map(env.tools_for("pm", chat_id=1))

    # Schedule next check for MSFT (no open position in FakeBroker)
    future_time = test_setup["now"] + timedelta(days=3)
    tools["schedule_next_check"].execute(
        ToolCall(
            id="1",
            name="schedule_next_check",
            args={"ticker": "MSFT", "when": future_time.isoformat()},
        )
    )

    with pytest.raises(ValueError, match="no open position found"):
        tools["accept_order"].execute(
            ToolCall(
                id="2",
                name="accept_order",
                args={"ticker": "MSFT", "action": "sell", "reason": "Take profits"},
            )
        )


def test_pm_watchlist_tools(test_setup):
    env: AgentEnvironment = test_setup["env"]
    tools = _get_tool_map(env.tools_for("pm", chat_id=1))

    # Add to watchlist
    tools["watchlist_set"].execute(
        ToolCall(
            id="1",
            name="watchlist_set",
            args={"action": "add", "ticker": "NVDA", "note": "AI leader"},
        )
    )
    wl = tools["watchlist_get"].execute(ToolCall(id="2", name="watchlist_get", args={}))
    assert any(item["ticker"] == "NVDA" for item in wl)

    # Remove
    tools["watchlist_set"].execute(
        ToolCall(
            id="3",
            name="watchlist_set",
            args={"action": "remove", "ticker": "NVDA"},
        )
    )
    wl_after = tools["watchlist_get"].execute(ToolCall(id="4", name="watchlist_get", args={}))
    assert not any(item["ticker"] == "NVDA" for item in wl_after)


# -----------------------------------------------------------------------------
# 5. Logging Verification
# -----------------------------------------------------------------------------


def test_logging_to_injected_logger_and_db(test_setup):
    env: AgentEnvironment = test_setup["env"]
    db: OfficeDB = test_setup["db"]
    tools = _get_tool_map(env.tools_for("technical_analyst", chat_id=42))

    # Invoke quote tool
    tools["quote"].execute(ToolCall(id="1", name="quote", args={"ticker": "AAPL"}))

    # 1. Injected logger verification
    logs = test_setup["logs"]
    assert len(logs) > 0
    latest_log = logs[-1]
    assert latest_log[0] == "technical_analyst"
    assert latest_log[1] == 42
    assert latest_log[2] == "quote"
    assert latest_log[3] == {"ticker": "AAPL"}
    assert latest_log[5] is None

    # 2. OfficeDB tool_calls table verification
    rows = db.connection.execute(
        "SELECT * FROM tool_calls WHERE tool = 'quote' ORDER BY id DESC LIMIT 1"
    ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["agent"] == "technical_analyst"
    assert row["chat_id"] == 42
    assert json.loads(row["params_json"]) == {"ticker": "AAPL"}


def test_send_message_canonicalizes_pm_and_rejects_unknown_recipient(test_setup):
    env: AgentEnvironment = test_setup["env"]
    db: OfficeDB = test_setup["db"]
    tools = _get_tool_map(env.tools_for("technical_analyst", chat_id=1))

    res = tools["send_message"].execute(
        ToolCall(
            id="1",
            name="send_message",
            args={"to_agent": "pm", "ticker_or_theme": "AAPL", "text": "Setup pronto"},
        )
    )
    assert db.get_chat(res["chat_id"])["agent"] == "portfolio_manager"

    with pytest.raises(ValueError, match="destinatario sconosciuto"):
        tools["send_message"].execute(
            ToolCall(
                id="2",
                name="send_message",
                args={"to_agent": "banana_agent", "ticker_or_theme": "AAPL", "text": "x"},
            )
        )
