"""Agent Office execution environment and tool generation."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from typing import Any, Protocol, runtime_checkable

from agents.backend import ToolSpec
from analysis.indicators import (
    average_true_range,
    exponential_moving_average,
    moving_average_convergence_divergence,
    pivot_points,
    relative_strength_index,
    simple_moving_average,
)
from execution.order_draft import (
    DEFAULT_K_STOP,
    DEFAULT_K_TP,
    DraftNotViable,
    OrderDraftInputs,
    build_order_draft,
    default_k_entry,
)
from storage.office_db import OfficeDB
from tools import schemas
from workflows.scheduling import clamp_schedule_date

logger = logging.getLogger(__name__)


@runtime_checkable
class MarketData(Protocol):
    """Protocol for financial market data provider returning plain dicts/lists."""

    def quote(self, symbol: str) -> dict[str, Any]: ...

    def ohlcv(
        self, symbol: str, interval: str = "1d", limit: int = 100
    ) -> list[dict[str, Any]]: ...

    def news(
        self, symbol: str | None = None, theme: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]: ...

    def ratings(self, symbol: str) -> list[dict[str, Any]] | dict[str, Any]: ...

    def insiders(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]: ...

    def financials(self, symbol: str) -> dict[str, Any] | list[dict[str, Any]]: ...

    def earnings_dates(self, symbol: str) -> list[dict[str, Any]] | dict[str, Any]: ...

    def macro(self, series_id: str) -> list[dict[str, Any]] | dict[str, Any]: ...

    def econ_calendar(self, limit: int = 20) -> list[dict[str, Any]]: ...

    def sector_perf(self) -> list[dict[str, Any]] | dict[str, Any]: ...


@runtime_checkable
class BrokerReader(Protocol):
    """Protocol for reading account, positions, and orders from a broker."""

    def get_account(self) -> Any: ...

    def get_positions(self) -> tuple[Any, ...] | list[Any]: ...

    def get_orders(self, query: Any = None) -> tuple[Any, ...] | list[Any]: ...


def _serialize(obj: Any) -> Any:
    """Helper to convert dataclasses, Decimals, datetimes to JSON-friendly structures."""
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat().replace("+00:00", "Z")
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    if hasattr(obj, "model_dump"):
        return _serialize(obj.model_dump())
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


_MESSAGEABLE_AGENTS = (
    "portfolio_manager",
    "sentiment_analyst",
    "technical_analyst",
    "fundamental_analyst",
    "risk_analyst",
    "market_analyst",
)

class AgentEnvironment:
    """Agent tool environment providing role-scoped, validated tools."""

    def __init__(
        self,
        db: OfficeDB,
        market_data: MarketData,
        broker_reader: BrokerReader,
        clock: Callable[[], datetime] | None = None,
        now: Callable[[], datetime] | datetime | None = None,
        logger: (
            Callable[[str, int | None, str, dict[str, Any], Any, str | None], Any] | None
        ) = None,
        subagent_caller: Callable[[str], Any] | None = None,
        on_accept: Callable[[str, str, str], Any] | None = None,
        calendar: Any = None,
        min_trading_days: int = 1,
        max_trading_days: int = 60,
        bar_timeframe: str = "1h",
    ) -> None:
        self.db = db
        self.market_data = market_data
        self.broker_reader = broker_reader
        self._clock = clock
        self._now = now
        self.logger = logger
        self.subagent_caller = subagent_caller
        self.on_accept = on_accept
        self.calendar = calendar
        self.min_trading_days = min_trading_days
        self.max_trading_days = max_trading_days
        self.bar_timeframe = bar_timeframe

    def get_now(self) -> datetime:
        """Return current UTC datetime from injected clock or system time."""
        if self._now is not None:
            t = self._now() if callable(self._now) else self._now
        elif self._clock is not None:
            t = self._clock()
        else:
            t = datetime.now(UTC)
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        return t

    def _now_iso(self) -> str:
        return self.get_now().isoformat().replace("+00:00", "Z")

    def _normalize_role(self, agent_name: str) -> str:
        """Map agent name to canonical role."""
        name = agent_name.lower().strip()
        if name.startswith("ticker:"):
            return "ticker_agent"
        if name in ("pm", "portfolio_manager"):
            return "pm"
        if "market" in name:
            return "market_analyst"
        if "sentiment" in name:
            return "sentiment_analyst"
        if "technical" in name:
            return "technical_analyst"
        if "fundamental" in name:
            return "fundamental_analyst"
        if "risk" in name:
            return "risk_analyst"
        if "subagent" in name:
            return "subagent"

        # Check in DB if registered
        reg = self.db.get_agent(agent_name)
        if reg and reg.get("role"):
            r = reg["role"].lower().strip()
            if r in ("pm", "portfolio_manager"):
                return "pm"
            if "market" in r:
                return "market_analyst"
            if "sentiment" in r:
                return "sentiment_analyst"
            if "technical" in r:
                return "technical_analyst"
            if "fundamental" in r:
                return "fundamental_analyst"
            if "risk" in r:
                return "risk_analyst"
            if "subagent" in r:
                return "subagent"
            return r
        return name

    def _log_tool_call(
        self,
        agent_name: str,
        chat_id: int | None,
        tool_name: str,
        params: dict[str, Any],
        result: Any,
        error: str | None,
        duration_ms: int | None = None,
        cycle_id: int | None = None,
    ) -> None:
        """Log tool invocation to OfficeDB and injected logger."""
        try:
            self.db.log_tool_call(
                agent=agent_name,
                tool=tool_name,
                params=_serialize(params),
                result=_serialize(result) if result is not None else {},
                error=error,
                chat_id=chat_id,
                ts=self._now_iso(),
                duration_ms=duration_ms,
                cycle_id=cycle_id,
            )
        except Exception as e:
            logger.warning(f"Failed to record tool call in OfficeDB: {e}")

        if self.logger is not None:
            try:
                self.logger(agent_name, chat_id, tool_name, params, result, error)
            except Exception as e:
                logger.warning(f"Injected tool logger failed: {e}")

    def _make_tool(
        self,
        name: str,
        description: str,
        input_model: type[schemas.BaseModel],
        handler: Callable[..., Any],
        agent_name: str,
        chat_id: int | None,
        cycle_id: int | None = None,
    ) -> ToolSpec:
        """Wrap a tool function with logging and error tracking."""
        def wrapped(**kwargs: Any) -> Any:
            started = time.monotonic()
            if getattr(self.db, "event_log", None):
                self.db.event_log.append(
                    "tool.started",
                    f"tool:{agent_name}:{name}",
                    {
                        "agent": agent_name,
                        "tool": name,
                        "chat_id": chat_id,
                        "cycle_id": cycle_id,
                        "params": _serialize(kwargs),
                        "ts": self._now_iso(),
                    },
                    actor=agent_name,
                )
            try:
                res = handler(**kwargs)
                dur = int((time.monotonic() - started) * 1000)
                self._log_tool_call(agent_name, chat_id, name, kwargs, res, None,
                                    dur, cycle_id)
                if getattr(self.db, "event_log", None):
                    self.db.event_log.append(
                        "tool.finished",
                        f"tool:{agent_name}:{name}",
                        {
                            "agent": agent_name,
                            "tool": name,
                            "chat_id": chat_id,
                            "cycle_id": cycle_id,
                            "duration_ms": dur,
                            "success": True,
                            "error": None,
                            "ts": self._now_iso(),
                        },
                        actor=agent_name,
                    )
                return res
            except Exception as exc:
                err_msg = str(exc)
                dur = int((time.monotonic() - started) * 1000)
                self._log_tool_call(agent_name, chat_id, name, kwargs, None, err_msg,
                                    dur, cycle_id)
                if getattr(self.db, "event_log", None):
                    self.db.event_log.append(
                        "tool.finished",
                        f"tool:{agent_name}:{name}",
                        {
                            "agent": agent_name,
                            "tool": name,
                            "chat_id": chat_id,
                            "cycle_id": cycle_id,
                            "duration_ms": dur,
                            "success": False,
                            "error": err_msg,
                            "ts": self._now_iso(),
                        },
                        actor=agent_name,
                    )
                raise

        return ToolSpec(
            name=name,
            description=description,
            input_model=input_model,
            fn=wrapped,
        )

    def _get_or_create_ticker_state(self, ticker: str) -> dict[str, Any]:
        """Fetch and deserialise ticker_state or return an empty template."""
        row = self.db.get_ticker_state(ticker)
        if not row or not row.get("state_json"):
            return {
                "ticker": ticker.upper(),
                "analyses": {},
                "suggestions": {},
                "coefficients": {},
                "draft": None,
                "decision": None,
            }
        try:
            return json.loads(row["state_json"])
        except Exception:
            return {
                "ticker": ticker.upper(),
                "analyses": {},
                "suggestions": {},
                "coefficients": {},
                "draft": None,
                "decision": None,
            }

    def decide_proposal(self, proposal_id: int, action: str, reason: str, when: str | None, actor: str) -> dict[str, Any]:
        if action not in ("accept", "defer", "reject", "ask"):
            raise ValueError("Unknown proposal action")
        if not reason.strip():
            raise ValueError("Decision reason is required")
        if action == "defer":
            if not when:
                raise ValueError("Defer requires a future check date")
            requested = datetime.fromisoformat(when.replace("Z", "+00:00"))
            if requested.tzinfo is None:
                raise ValueError("Check date must include a timezone")
            if requested <= self.get_now():
                raise ValueError("Check date must be in the future")
            scheduled = clamp_schedule_date(requested, self.get_now(), self.min_trading_days,
                                            self.max_trading_days, self.calendar)
        now = self._now_iso()
        with self.db.transaction():
            row = self.db.connection.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            if not row or row["status"] != "pending":
                raise ValueError("Proposal is not pending")

            status = {"accept": "accepted", "defer": "deferred", "reject": "rejected", "ask": "asked"}[action]
            if action == "accept" and row["direction"] not in ("buy", "sell"):
                raise ValueError("Only buy or sell proposals can be accepted")
            self.db.connection.execute(
                "UPDATE proposals SET status=?, decided_ts=?, decided_by=?, reason=? WHERE id=? AND status='pending'",
                (status, now, actor, reason.strip(), proposal_id),
            )
            sym = row["ticker"]
            if action == "defer":
                self.db.enqueue_scheduled_task(agent="portfolio_manager", chat=sym,
                    when_ts=scheduled.isoformat().replace("+00:00", "Z"), source="agent",
                    reason=reason.strip(), data={"ticker": sym})
            if action == "ask":
                chat = self.db.get_or_create_chat(row["agent"], sym)
                self.db.append_message(chat_id=chat, author=actor, text=reason.strip(),
                                       kind="original", cycle_id=row["cycle_id"], ts=now)
            self.db.write_dossier_section(sym, "status", {
                "accepted": "approved", "deferred": "monitoring", "rejected": "declined", "asked": "analyzing"
            }[status], actor, now)
            previous = self.db.connection.execute(
                "SELECT document_json FROM dossier_versions WHERE ticker=? ORDER BY version DESC LIMIT 1", (sym,)
            ).fetchone()
            prior_proposal = json.loads(previous["document_json"]).get("proposal", {}) if previous else {}
            self.db.write_dossier_section(sym, "proposal", {**prior_proposal, "id": proposal_id,
                "status": status, "submitted_ts": row["submitted_ts"]}, actor, now)
            self.db.write_dossier_section(sym, "decisions", {
                "ts": now, "actor": actor, "action": action, "reason": reason.strip(),
                "cycle_id": row["cycle_id"],
            }, actor, now)
            if self.db.event_log:
                self.db.event_log.append("proposal.decided", f"proposal:{proposal_id}",
                    {"id": proposal_id, "ticker": sym, "action": action, "status": status}, actor)
        return {"id": proposal_id, "status": status}

    def _increment_cycle_budget(self, cycle_id: int | None, category: str) -> None:
        """Increment message or subagent call counters in cycle budget_used_json."""
        if cycle_id is None:
            return
        row = self.db.get_cycle(cycle_id)
        if not row:
            return
        budget_used = {}
        if row.get("budget_used_json"):
            try:
                budget_used = json.loads(row["budget_used_json"])
            except Exception:
                budget_used = {}
        budget_used[category] = budget_used.get(category, 0) + 1
        budget_used["total"] = budget_used.get("total", 0) + 1
        self.db.connection.execute(
            "UPDATE cycles SET budget_used_json = ? WHERE id = ?",
            (json.dumps(budget_used), cycle_id),
        )

    def current_draft(self, ticker: str) -> dict[str, Any]:
        state = self._get_or_create_ticker_state(ticker)
        self._recompute_draft_if_possible(ticker, state)
        return {"ticker": ticker, "draft": state.get("draft")}

    def _recompute_draft_if_possible(self, ticker: str, state: dict[str, Any]) -> None:
        """Deterministically recompute the order draft if minimal inputs exist."""
        ticker = ticker.upper().strip()
        # 1. Determine direction & conviction
        direction = None
        conviction = Decimal("0.5")

        decision = state.get("decision")
        if decision and isinstance(decision, dict) and decision.get("action") in ("buy", "sell"):
            direction = decision["action"]

        if not direction:
            p_row = self.db.connection.execute(
                "SELECT direction, conviction FROM proposals WHERE ticker = ? ORDER BY id DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            if p_row and p_row["direction"] in ("buy", "sell"):
                direction = p_row["direction"]
                try:
                    conviction = Decimal(str(p_row["conviction"]))
                except Exception:
                    pass
        if not direction:
            suggestions = state.get("suggestions", {})
            for sug in suggestions.values():
                if isinstance(sug, dict) and sug.get("direction") in ("buy", "sell"):
                    direction = sug["direction"]
                    if "conviction" in sug:
                        try:
                            conviction = Decimal(str(sug["conviction"]))
                        except Exception:
                            pass
                    break

        if not direction:
            return

        # 2. Price
        try:
            quote_data = self.market_data.quote(ticker)
            price_val = (
                quote_data.get("price")
                or quote_data.get("c")
                or quote_data.get("close")
            )
            if price_val is None:
                return
            current_price = Decimal(str(price_val))
            if current_price <= Decimal("0"):
                return
        except Exception:
            return

        # 3. ATR
        atr = None
        try:
            bars = self.market_data.ohlcv(ticker, interval="1d", limit=30)
            if len(bars) >= 15:
                highs = [Decimal(str(b["h"])) for b in bars]
                lows = [Decimal(str(b["l"])) for b in bars]
                closes = [Decimal(str(b["c"])) for b in bars]
                atr_vals = average_true_range(highs, lows, closes, window=14)
                if atr_vals:
                    atr = atr_vals[-1]
        except Exception:
            pass

        if atr is None:
            if "atr" in quote_data:
                try:
                    atr = Decimal(str(quote_data["atr"]))
                except Exception:
                    pass
            elif "atr" in state.get("coefficients", {}):
                try:
                    atr = Decimal(str(state["coefficients"]["atr"]))
                except Exception:
                    pass

        if atr is None or atr <= Decimal("0"):
            return

        # 4. Equity
        try:
            account = self.broker_reader.get_account()
            eq_val = getattr(account, "equity", None)
            if eq_val is None and isinstance(account, dict):
                eq_val = account.get("equity")
            if eq_val is None:
                return
            equity = Decimal(str(eq_val))
            if equity <= Decimal("0"):
                return
        except Exception:
            return

        # 5. Position quantity for sell
        position_quantity = None
        if direction == "sell":
            try:
                positions = self.broker_reader.get_positions()
                matching = None
                for p in positions:
                    sym = getattr(p, "symbol", "") if hasattr(p, "symbol") else p.get("symbol", "")
                    if sym.upper() == ticker:
                        matching = p
                        break
                if matching is None:
                    return
                qty = (
                    getattr(matching, "quantity", None)
                    if hasattr(matching, "quantity")
                    else matching.get("quantity")
                )
                if qty is None:
                    return
                position_quantity = Decimal(str(qty))
                if position_quantity <= Decimal("0"):
                    return
            except Exception:
                return

        # 6. Coefficients
        coeffs = state.get("coefficients", {})
        if "k_entry" in coeffs and coeffs["k_entry"] is not None:
            k_entry = Decimal(str(coeffs["k_entry"]))
        else:
            k_entry = default_k_entry(conviction)

        risk_fraction = (
            Decimal(str(coeffs["risk_fraction"]))
            if coeffs.get("risk_fraction") is not None
            else Decimal("0.01")
        )
        k_stop = (
            Decimal(str(coeffs["k_stop"]))
            if coeffs.get("k_stop") is not None
            else DEFAULT_K_STOP
        )
        k_tp = (
            Decimal(str(coeffs["k_tp"]))
            if coeffs.get("k_tp") is not None
            else DEFAULT_K_TP
        )

        try:
            inputs = OrderDraftInputs(
                symbol=ticker,
                side=direction,
                current_price=current_price,
                atr=atr,
                equity=equity,
                risk_fraction=risk_fraction,
                k_entry=k_entry,
                k_stop=k_stop,
                k_tp=k_tp,
                position_quantity=position_quantity,
            )
            draft = build_order_draft(inputs)
            state["draft"] = {
                "symbol": draft.symbol,
                "side": draft.side,
                "entry": float(draft.entry),
                "stop": float(draft.stop) if draft.stop is not None else None,
                "take_profit": float(draft.take_profit) if draft.take_profit is not None else None,
                "quantity": float(draft.quantity),
                "risk_reward": float(draft.risk_reward) if draft.risk_reward is not None else None,
                "risk_amount": float(draft.risk_amount) if draft.risk_amount is not None else None,
                "notional": float(draft.notional),
                "draft_hash": draft.draft_hash,
            }
        except (DraftNotViable, ValueError):
            pass

    def _has_future_scheduled_task(self, ticker: str) -> bool:
        """Check whether a pending scheduled task exists for ticker in the future."""
        now_ts = self._now_iso()
        sym = ticker.upper().strip()
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
        return row is not None

    def tools_for(
        self, agent_name: str, chat_id: int | None = None, cycle_id: int | None = None
    ) -> list[ToolSpec]:
        """Generate list of ToolSpec tailored to the given agent and chat context."""
        role = self._normalize_role(agent_name)
        make_tool = partial(self._make_tool, cycle_id=cycle_id)
        tools: list[ToolSpec] = []

        # ---------------------------------------------------------------------
        # Universal Tools: read_state, read_portfolio
        # ---------------------------------------------------------------------

        def handle_read_state(ticker: str) -> dict[str, Any]:
            sym = ticker.upper().strip()
            return self._get_or_create_ticker_state(sym)

        tools.append(
            make_tool(
                name="read_state",
                description=(
                    "Read shared state for a ticker (analyses, suggestions, coefficients, "
                    "draft, decision)."
                ),
                input_model=schemas.ReadStateInput,
                handler=handle_read_state,
                agent_name=agent_name,
                chat_id=chat_id,
            )
        )

        def handle_read_dossier(ticker: str) -> dict[str, Any]:
            row = self.db.connection.execute(
                "SELECT document_json FROM dossier_versions WHERE ticker = ? "
                "ORDER BY version DESC LIMIT 1", (ticker.upper().strip(),)
            ).fetchone()
            return json.loads(row["document_json"]) if row else {}

        def handle_news_search(q: str | None = None, ticker: str | None = None, since: str | None = None, limit: int = 50) -> Any:
            items = self.db.query_news(ticker=ticker, q=q, since=since, limit=limit)
            for it in items:
                try:
                    self.db.log_news_usage(news_id=it["id"], agent=agent_name, kind="read", cycle_id=cycle_id, chat_id=chat_id)
                except Exception:
                    pass
            return _serialize(items)

        def handle_economic_calendar(from_ts: str | None = None, to_ts: str | None = None) -> Any:
            return _serialize(self.db.query_calendar(kind="macro", from_ts=from_ts, to_ts=to_ts))

        def handle_earnings_calendar(from_ts: str | None = None, to_ts: str | None = None, tickers: list[str] | None = None) -> Any:
            return _serialize(self.db.query_calendar(kind="earnings", from_ts=from_ts, to_ts=to_ts, tickers=tickers))

        def handle_news_by_ticker_db(ticker: str, limit: int = 10) -> Any:
            items = self.db.query_news(ticker=ticker, limit=limit)
            if not items and self.market_data:
                try:
                    return _serialize(self.market_data.news(symbol=ticker.upper().strip(), limit=limit))
                except Exception:
                    return []
            for it in items:
                try:
                    self.db.log_news_usage(news_id=it["id"], agent=agent_name, kind="read", cycle_id=cycle_id, chat_id=chat_id)
                except Exception:
                    pass
            return _serialize(items)

        def handle_news_by_theme_db(theme: str, limit: int = 10) -> Any:
            items = self.db.query_news(theme=theme, limit=limit)
            if not items and self.market_data:
                try:
                    return _serialize(self.market_data.news(theme=theme.strip(), limit=limit))
                except Exception:
                    return []
            for it in items:
                try:
                    self.db.log_news_usage(news_id=it["id"], agent=agent_name, kind="read", cycle_id=cycle_id, chat_id=chat_id)
                except Exception:
                    pass
            return _serialize(items)

        # Universal news search and calendar tools for analysts and PM
        tools.append(
            make_tool(
                name="news_search",
                description="Search news archive by query, ticker, or timestamp.",
                input_model=schemas.NewsSearchInput,
                handler=handle_news_search,
                agent_name=agent_name,
                chat_id=chat_id,
            )
        )
        tools.append(
            make_tool(
                name="economic_calendar",
                description="Fetch economic calendar events.",
                input_model=schemas.EconomicCalendarInput,
                handler=handle_economic_calendar,
                agent_name=agent_name,
                chat_id=chat_id,
            )
        )
        tools.append(
            make_tool(
                name="earnings_calendar",
                description="Fetch earnings calendar events.",
                input_model=schemas.EarningsCalendarInput,
                handler=handle_earnings_calendar,
                agent_name=agent_name,
                chat_id=chat_id,
            )
        )

        tools.append(make_tool(
            name="read_dossier", description="Read the ticker dossier and senior colleague notes.",
            input_model=schemas.ReadStateInput, handler=handle_read_dossier,
            agent_name=agent_name, chat_id=chat_id,
        ))

        def handle_read_portfolio() -> dict[str, Any]:
            account = self.broker_reader.get_account()
            positions = self.broker_reader.get_positions()
            orders = self.broker_reader.get_orders()
            return {
                "account": _serialize(account),
                "positions": _serialize(positions),
                "orders": _serialize(orders),
            }

        tools.append(
            make_tool(
                name="read_portfolio",
                description=(
                    "Read portfolio account equity, cash, positions, and open/recent orders."
                ),
                input_model=schemas.ReadPortfolioInput,
                handler=handle_read_portfolio,
                agent_name=agent_name,
                chat_id=chat_id,
            )
        )

        # Subagent tools can NEVER send messages or create orders
        if role != "subagent":
            def handle_send_message(
                to_agent: str, ticker_or_theme: str, text: str
            ) -> dict[str, Any]:
                target_role = self._normalize_role(to_agent.strip())
                canonical = {"pm": "portfolio_manager"}.get(target_role, target_role)
                ticker_target = to_agent.strip() if to_agent.strip().startswith("ticker:") else None
                if ticker_target:
                    canonical = ticker_target
                    if canonical != f"ticker:{ticker_or_theme.upper().strip()}":
                        raise ValueError("Ticker recipient must match the chat topic")
                if canonical not in _MESSAGEABLE_AGENTS and not ticker_target:
                    raise ValueError(
                        f"destinatario sconosciuto '{to_agent}'. Validi: "
                        f"{', '.join(_MESSAGEABLE_AGENTS)}"
                    )
                target_agent = canonical
                topic = ticker_or_theme.strip()

                if role == "ticker_agent" and agent_name != f"ticker:{topic.upper()}":
                    raise ValueError("Ticker agent cannot message another ticker")

                # If request is to Market Analyst on a ticker, deliver into the chat of the
                # ticker's SECTOR
                if target_role == "market_analyst":
                    row = self.db.connection.execute(
                        "SELECT sector FROM securities WHERE UPPER(symbol) = UPPER(?)",
                        (topic,),
                    ).fetchone()
                    if row and row["sector"]:
                        topic = row["sector"]

                dest_chat_id = self.db.get_or_create_chat(target_agent, topic)
                msg_id = self.db.append_message(
                    chat_id=dest_chat_id,
                    author=agent_name,
                    text=text,
                    kind="original",
                    cycle_id=cycle_id,
                    ts=self._now_iso(),
                )
                self._increment_cycle_budget(cycle_id, "messages")
                return {
                    "status": "delivered",
                    "to_agent": target_agent,
                    "chat_id": dest_chat_id,
                    "topic": topic,
                    "message_id": msg_id,
                }

            tools.append(
                make_tool(
                    name="send_message",
                    description=(
                        "Send a message to another agent. If sent to market_analyst on a ticker, "
                        "delivers into the sector chat."
                    ),
                    input_model=schemas.SendMessageInput,
                    handler=handle_send_message,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_call_subagent(task: str) -> dict[str, Any]:
                self._increment_cycle_budget(cycle_id, "subagents")
                if self.subagent_caller is not None:
                    result = self.subagent_caller(task)
                else:
                    result = f"Delegated subagent task: {task}"
                return {"task": task, "result": _serialize(result)}

            tools.append(
                make_tool(
                    name="call_subagent",
                    description="Delegate a bounded read-only task to a subagent.",
                    input_model=schemas.CallSubagentInput,
                    handler=handle_call_subagent,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

        if role == "ticker_agent":
            def handle_write_lesson(ticker: str, text: str, exit_reason: str | None = None) -> dict[str, Any]:
                sym = ticker.upper().strip()
                if agent_name != f"ticker:{sym}" or not text.strip() or "\n" in text:
                    raise ValueError("Lesson must be one line for your own ticker")
                ts = self._now_iso()
                version = self.db.write_dossier_section(sym, "lessons", {"text": text.strip(),
                    "exit_reason": exit_reason}, agent_name, ts)
                return {"ticker": sym, "version": version}

            tools.append(make_tool(name="write_lesson", description="Record a one-line lesson from the previous outcome.",
                                   input_model=schemas.WriteLessonInput, handler=handle_write_lesson,
                                   agent_name=agent_name, chat_id=chat_id))

            def handle_write_thesis(ticker: str, direction: str, conviction: float,
                                    pro: list[str], contro: list[str], time_horizon: str | None = None,
                                    catalysts: list[dict] | None = None, next_check_date: str | None = None) -> dict[str, Any]:
                sym = ticker.upper().strip()
                if agent_name != f"ticker:{sym}":
                    raise ValueError("Ticker agent can only write its own ticker")
                ts = self._now_iso()
                thesis = {"direction": direction, "conviction": conviction, "pro": pro, "contro": contro,
                          "time_horizon": time_horizon, "catalysts": catalysts or [], "next_check_date": next_check_date,
                          "author": agent_name, "ts": ts}
                version = self.db.write_dossier_section(sym, "thesis", thesis, agent_name, ts)
                return {"ticker": sym, "version": version}

            tools.append(make_tool(name="write_thesis", description="Update your ticker thesis.",
                                   input_model=schemas.WriteThesisInput, handler=handle_write_thesis,
                                   agent_name=agent_name, chat_id=chat_id))

            def handle_submit_proposal(ticker: str, direction: str, conviction: float, reason: str) -> dict[str, Any]:
                sym = ticker.upper().strip()
                if agent_name != f"ticker:{sym}":
                    raise ValueError("Ticker agent can only propose for its own ticker")
                if cycle_id is not None:
                    waiting = self.db.connection.execute(
                        "SELECT a.agent FROM chats a JOIN messages m ON m.chat_id = a.id "
                        "WHERE m.author = ? AND m.cycle_id = ? AND a.agent LIKE '%_analyst' "
                        "AND NOT EXISTS (SELECT 1 FROM messages r WHERE r.cycle_id = ? AND r.author = a.agent AND r.id > m.id) LIMIT 1",
                        (agent_name, cycle_id, cycle_id),
                    ).fetchone()
                    if waiting:
                        raise ValueError(f"Await specialist reply: {waiting['agent']}")
                    existing = self.db.connection.execute(
                        "SELECT id FROM proposals WHERE cycle_id=? AND status IN ('pending','accepted') LIMIT 1", (cycle_id,)
                    ).fetchone()
                    if existing:
                        raise ValueError("Cycle already has an open proposal")
                if not reason.strip():
                    raise ValueError("Proposal reason is required")
                now = self._now_iso()
                with self.db.transaction():
                    cursor = self.db.connection.execute(
                        "INSERT INTO proposals (ticker, agent, status, direction, conviction, submitted_ts, reason, cycle_id) "
                        "VALUES (?, ?, 'pending', ?, ?, ?, ?, ?)",
                        (sym, agent_name, direction, conviction, now, reason.strip(), cycle_id),
                    )
                    proposal_id = int(cursor.lastrowid)
                    self.db.write_dossier_section(sym, "status", "proposed", agent_name, now)
                    state = self._get_or_create_ticker_state(sym)
                    coeff = state.get("coefficients", {})
                    self.db.write_dossier_section(sym, "proposal", {
                        "id": proposal_id, "status": "pending", "k_entry": coeff.get("k_entry"),
                        "k_stop": coeff.get("k_stop"), "k_tp": coeff.get("k_tp"),
                        "entry_price": None, "stop_price": None, "target_price": None,
                        "sizing_fraction": None, "risk_reward": None, "submitted_ts": now,
                    }, agent_name, now)
                    pm_chat = self.db.get_or_create_chat("portfolio_manager", sym)
                    self.db.append_message(chat_id=pm_chat, author=agent_name,
                                           text=f"Proposta #{proposal_id} per {sym}: {reason.strip()}",
                                           cycle_id=cycle_id, ts=now)
                    self._increment_cycle_budget(cycle_id, "messages")
                    if self.db.event_log is not None:
                        self.db.event_log.append("proposal.submitted", f"proposal:{proposal_id}",
                                                 {"id": proposal_id, "ticker": sym}, agent_name)
                return {"id": proposal_id, "status": "pending"}

            tools.append(make_tool(name="submit_proposal", description="Submit a proposal to the PM, without placing an order.",
                                   input_model=schemas.SubmitProposalInput, handler=handle_submit_proposal,
                                   agent_name=agent_name, chat_id=chat_id))

        # ---------------------------------------------------------------------
        # Analyst Tools: write_analysis, suggest, set_coefficients
        # ---------------------------------------------------------------------
        is_analyst = role in (
            "market_analyst",
            "sentiment_analyst",
            "technical_analyst",
            "fundamental_analyst",
            "risk_analyst",
        )

        if is_analyst:
            def handle_write_analysis(ticker: str, section_text: str) -> dict[str, Any]:
                sym = ticker.upper().strip()
                state = self._get_or_create_ticker_state(sym)
                analyses = state.setdefault("analyses", {})
                analyses[agent_name] = section_text
                self._recompute_draft_if_possible(sym, state)
                with self.db.transaction():
                    self.db.set_ticker_state(sym, state, updated_ts=self._now_iso())
                    self.db.write_dossier_section(sym, "desks", {
                        "agent": agent_name, "section": role, "text": section_text,
                        "ts": self._now_iso(), "reference_date": self._now_iso()[:10],
                        "confidence": None, "status": "active",
                    }, agent_name, self._now_iso())
                return {"status": "ok", "ticker": sym, "agent": agent_name}

            tools.append(
                make_tool(
                    name="write_analysis",
                    description="Update your specialist analysis section in the ticker state.",
                    input_model=schemas.WriteAnalysisInput,
                    handler=handle_write_analysis,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_suggest(ticker: str, direction: str, conviction: float) -> dict[str, Any]:
                sym = ticker.upper().strip()
                dir_val = direction.lower().strip()
                if dir_val not in ("buy", "sell", "hold"):
                    raise ValueError(
                        f"Invalid direction: {direction}. Must be 'buy', 'sell', or 'hold'"
                    )
                if conviction < 0.0 or conviction > 1.0:
                    raise ValueError(f"Conviction must be between 0.0 and 1.0, got {conviction}")

                state = self._get_or_create_ticker_state(sym)
                suggestions = state.setdefault("suggestions", {})
                suggestions[agent_name] = {"direction": dir_val, "conviction": float(conviction)}
                self._recompute_draft_if_possible(sym, state)
                self.db.set_ticker_state(sym, state, updated_ts=self._now_iso())
                return {
                    "status": "ok",
                    "ticker": sym,
                    "agent": agent_name,
                    "direction": dir_val,
                    "conviction": float(conviction),
                }

            tools.append(
                make_tool(
                    name="suggest",
                    description="Suggest trading direction (buy/sell/hold) and conviction (0..1).",
                    input_model=schemas.SuggestInput,
                    handler=handle_suggest,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_set_coefficients(
                ticker: str,
                k_entry: float | None = None,
                risk_fraction: float | None = None,
                k_stop: float | None = None,
                k_tp: float | None = None,
                k_trail_act: float | None = None,
                k_trail: float | None = None,
            ) -> dict[str, Any]:
                sym = ticker.upper().strip()

                # Competence check
                if role == "risk_analyst":
                    if any(v is not None for v in (k_stop, k_tp, k_trail_act, k_trail)):
                        raise ValueError(
                            "risk_analyst may only set k_entry and risk_fraction"
                        )
                    if k_entry is None and risk_fraction is None:
                        raise ValueError("Must provide k_entry or risk_fraction")
                elif role == "technical_analyst":
                    if any(v is not None for v in (k_entry, risk_fraction)):
                        raise ValueError(
                            "technical_analyst may only set k_stop, k_tp, k_trail_act, k_trail"
                        )
                    if k_stop is None and k_tp is None and k_trail_act is None and k_trail is None:
                        raise ValueError("Must provide at least one technical coefficient")
                else:
                    raise ValueError(
                        f"Agent {agent_name} ({role}) is not authorized to set coefficients"
                    )

                # Bounds checking
                if k_entry is not None and (k_entry < 0.0 or k_entry > 10.0):
                    raise ValueError(f"k_entry out of bounds [0.0, 10.0]: {k_entry}")
                if risk_fraction is not None and (risk_fraction <= 0.0 or risk_fraction > 1.0):
                    raise ValueError(f"risk_fraction out of bounds (0.0, 1.0]: {risk_fraction}")
                if k_stop is not None and (k_stop <= 0.0 or k_stop > 20.0):
                    raise ValueError(f"k_stop out of bounds (0.0, 20.0]: {k_stop}")
                if k_tp is not None and (k_tp <= 0.0 or k_tp > 50.0):
                    raise ValueError(f"k_tp out of bounds (0.0, 50.0]: {k_tp}")
                if k_trail_act is not None and (k_trail_act <= 0.0 or k_trail_act > 20.0):
                    raise ValueError(f"k_trail_act out of bounds (0.0, 20.0]: {k_trail_act}")
                if k_trail is not None and (k_trail <= 0.0 or k_trail > 20.0):
                    raise ValueError(f"k_trail out of bounds (0.0, 20.0]: {k_trail}")

                state = self._get_or_create_ticker_state(sym)
                coeffs = state.setdefault("coefficients", {})
                if k_entry is not None:
                    coeffs["k_entry"] = float(k_entry)
                if risk_fraction is not None:
                    coeffs["risk_fraction"] = float(risk_fraction)
                if k_stop is not None:
                    coeffs["k_stop"] = float(k_stop)
                if k_tp is not None:
                    coeffs["k_tp"] = float(k_tp)
                if k_trail_act is not None:
                    coeffs["k_trail_act"] = float(k_trail_act)
                if k_trail is not None:
                    coeffs["k_trail"] = float(k_trail)

                self._recompute_draft_if_possible(sym, state)
                self.db.set_ticker_state(sym, state, updated_ts=self._now_iso())
                return {"status": "ok", "ticker": sym, "coefficients": coeffs}

            tools.append(
                make_tool(
                    name="set_coefficients",
                    description=(
                        "Set order calculation coefficients strictly by competence and bounds "
                        "(Risk Analyst: k_entry, risk_fraction; Technical Analyst: k_stop, k_tp, "
                        "k_trail_act, k_trail)."
                    ),
                    input_model=schemas.SetCoefficientsInput,
                    handler=handle_set_coefficients,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

        # ---------------------------------------------------------------------
        # Data Tools: Market Analyst
        # ---------------------------------------------------------------------
        if role == "market_analyst":
            def handle_macro(series_id: str) -> Any:
                return _serialize(self.market_data.macro(series_id.strip()))

            tools.append(
                make_tool(
                    name="macro",
                    description="Fetch macroeconomic time series data.",
                    input_model=schemas.MacroInput,
                    handler=handle_macro,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_news_by_theme(theme: str, limit: int = 10) -> Any:
                return handle_news_by_theme_db(theme=theme, limit=limit)

            tools.append(
                make_tool(
                    name="news_by_theme",
                    description="Fetch news articles by macro or sector theme.",
                    input_model=schemas.NewsByThemeInput,
                    handler=handle_news_by_theme,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_econ_calendar(limit: int = 20) -> Any:
                return _serialize(self.market_data.econ_calendar(limit=limit))

            tools.append(
                make_tool(
                    name="econ_calendar",
                    description="Fetch upcoming economic calendar events.",
                    input_model=schemas.EconCalendarInput,
                    handler=handle_econ_calendar,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_sector_perf() -> Any:
                return _serialize(self.market_data.sector_perf())

            tools.append(
                make_tool(
                    name="sector_perf",
                    description="Fetch sector performance figures.",
                    input_model=schemas.SectorPerfInput,
                    handler=handle_sector_perf,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_set_sector_view(sector: str, view: str) -> dict[str, Any]:
                sec_clean = sector.strip()
                v_clean = view.strip()
                now_iso = self._now_iso()

                # 1. Record in sector_performance
                self.db.connection.execute(
                    """
                    INSERT INTO sector_performance (sector, ts, perf_json, source, fetched_at)
                    VALUES (?, ?, ?, 'market_analyst', ?)
                    ON CONFLICT(sector, ts, source) DO UPDATE SET
                        perf_json = excluded.perf_json,
                        fetched_at = excluded.fetched_at
                    """,
                    (sec_clean, now_iso[:10], v_clean, now_iso),
                )

                # 2. Update ticker_state for all securities belonging to this sector
                sec_rows = self.db.connection.execute(
                    "SELECT symbol FROM securities WHERE UPPER(sector) = UPPER(?)",
                    (sec_clean,),
                ).fetchall()
                updated_tickers = []
                for row in sec_rows:
                    sym = row["symbol"].upper()
                    st = self._get_or_create_ticker_state(sym)
                    st["sector_view"] = v_clean
                    self.db.set_ticker_state(sym, st, updated_ts=now_iso)
                    updated_tickers.append(sym)

                return {
                    "status": "updated",
                    "sector": sec_clean,
                    "view": v_clean,
                    "securities_updated": len(updated_tickers),
                    "tickers": updated_tickers,
                }

            tools.append(
                make_tool(
                    name="set_sector_view",
                    description=(
                        "Update the market outlook for a sector so cycles on tickers "
                        "in that sector receive it (US 77)."
                    ),
                    input_model=schemas.SetSectorViewInput,
                    handler=handle_set_sector_view,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_schedule_task(chat: str, when: str, reason: str) -> dict[str, Any]:
                try:
                    requested_dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
                except Exception as exc:
                    raise ValueError(f"Invalid ISO datetime format for 'when': {when}") from exc

                if requested_dt.tzinfo is None:
                    requested_dt = requested_dt.replace(tzinfo=UTC)

                clamped_dt = clamp_schedule_date(
                    requested=requested_dt,
                    now=self.get_now(),
                    min_trading_days=self.min_trading_days,
                    max_trading_days=self.max_trading_days,
                    calendar=self.calendar,
                )
                clamped_iso = clamped_dt.isoformat().replace("+00:00", "Z")
                task_id = self.db.enqueue_scheduled_task(
                    agent=agent_name,
                    chat=chat.strip(),
                    when_ts=clamped_iso,
                    source="agent",
                    reason=reason.strip(),
                )
                return {
                    "status": "scheduled",
                    "task_id": task_id,
                    "chat": chat.strip(),
                    "when": clamped_iso,
                    "reason": reason.strip(),
                }

            tools.append(
                make_tool(
                    name="schedule_task",
                    description=(
                        "Schedule a future task for Market Analyst with date clamped by "
                        "trading calendar."
                    ),
                    input_model=schemas.ScheduleTaskInput,
                    handler=handle_schedule_task,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

        # ---------------------------------------------------------------------
        # Data Tools: Sentiment Analyst
        # ---------------------------------------------------------------------
        if role == "sentiment_analyst":
            def handle_news_by_ticker(ticker: str, limit: int = 10) -> Any:
                return handle_news_by_ticker_db(ticker=ticker, limit=limit)

            tools.append(
                make_tool(
                    name="news_by_ticker",
                    description="Fetch recent news articles for a specific ticker.",
                    input_model=schemas.NewsByTickerInput,
                    handler=handle_news_by_ticker,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_ratings(ticker: str) -> Any:
                return _serialize(self.market_data.ratings(ticker.upper().strip()))

            tools.append(
                make_tool(
                    name="ratings",
                    description="Fetch analyst ratings for a ticker.",
                    input_model=schemas.RatingsInput,
                    handler=handle_ratings,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_insiders(ticker: str, limit: int = 20) -> Any:
                return _serialize(self.market_data.insiders(ticker.upper().strip(), limit=limit))

            tools.append(
                make_tool(
                    name="insiders",
                    description="Fetch insider trading transactions for a ticker.",
                    input_model=schemas.InsidersInput,
                    handler=handle_insiders,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

        # ---------------------------------------------------------------------
        # Data Tools: Technical Analyst
        # ---------------------------------------------------------------------
        if role == "technical_analyst":
            def handle_quote(ticker: str) -> Any:
                return _serialize(self.market_data.quote(ticker.upper().strip()))

            tools.append(
                make_tool(
                    name="quote",
                    description="Fetch current market quote for a ticker.",
                    input_model=schemas.QuoteInput,
                    handler=handle_quote,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_ohlcv(ticker: str, interval: str | None = None, limit: int = 100) -> Any:
                return _serialize(
                    self.market_data.ohlcv(ticker.upper().strip(), interval=interval or self.bar_timeframe, limit=limit)
                )

            tools.append(
                make_tool(
                    name="ohlcv",
                    description="Fetch historical OHLCV bars for a ticker.",
                    input_model=schemas.OHLCVInput,
                    handler=handle_ohlcv,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_indicators(
                ticker: str, indicators: list[str] | None = None
            ) -> dict[str, Any]:
                sym = ticker.upper().strip()
                bars = self.market_data.ohlcv(sym, interval=self.bar_timeframe, limit=150)
                if not bars:
                    return {"ticker": sym, "error": "No OHLCV bars available"}

                highs = [Decimal(str(b["h"])) for b in bars]
                lows = [Decimal(str(b["l"])) for b in bars]
                closes = [Decimal(str(b["c"])) for b in bars]

                req = [ind.upper() for ind in indicators] if indicators else [
                    "SMA",
                    "EMA",
                    "RSI",
                    "MACD",
                    "ATR",
                    "PIVOT",
                ]

                results: dict[str, Any] = {"ticker": sym}

                if "SMA" in req and len(closes) >= 20:
                    sma20 = simple_moving_average(closes, window=20)
                    results["sma20"] = float(sma20[-1]) if sma20 else None
                if "EMA" in req and len(closes) >= 20:
                    ema20 = exponential_moving_average(closes, window=20)
                    results["ema20"] = float(ema20[-1]) if ema20 else None
                if "RSI" in req and len(closes) > 14:
                    rsi14 = relative_strength_index(closes, window=14)
                    results["rsi14"] = float(rsi14[-1]) if rsi14 else None
                if "MACD" in req and len(closes) >= 26:
                    try:
                        macd_line, sig_line, hist = moving_average_convergence_divergence(closes)
                        results["macd"] = {
                            "macd": float(macd_line[-1]) if macd_line else None,
                            "signal": float(sig_line[-1]) if sig_line else None,
                            "hist": float(hist[-1]) if hist else None,
                        }
                    except Exception:
                        pass
                if "ATR" in req and len(closes) > 14:
                    atr14 = average_true_range(highs, lows, closes, window=14)
                    results["atr14"] = float(atr14[-1]) if atr14 else None
                if "PIVOT" in req and highs and lows and closes:
                    pivots = pivot_points(highs, lows, closes)
                    if pivots:
                        p, s1, s2, r1, r2 = pivots[-1]
                        results["pivot"] = {
                            "pivot": float(p),
                            "s1": float(s1),
                            "s2": float(s2),
                            "r1": float(r1),
                            "r2": float(r2),
                        }

                return results

            tools.append(
                make_tool(
                    name="indicators",
                    description=(
                        "Compute technical indicators on the fly (SMA, EMA, RSI, MACD, ATR, pivot)."
                    ),
                    input_model=schemas.IndicatorsInput,
                    handler=handle_indicators,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

        # ---------------------------------------------------------------------
        # Data Tools: Fundamental Analyst
        # ---------------------------------------------------------------------
        if role == "fundamental_analyst":
            def handle_financials(ticker: str) -> Any:
                return _serialize(self.market_data.financials(ticker.upper().strip()))

            tools.append(
                make_tool(
                    name="financials",
                    description="Fetch financial statements for a ticker.",
                    input_model=schemas.FinancialsInput,
                    handler=handle_financials,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_ratios(ticker: str) -> Any:
                fin = self.market_data.financials(ticker.upper().strip())
                if isinstance(fin, dict) and "ratios" in fin:
                    return _serialize(fin["ratios"])
                return _serialize(fin)

            tools.append(
                make_tool(
                    name="ratios",
                    description="Fetch financial ratios for a ticker.",
                    input_model=schemas.RatiosInput,
                    handler=handle_ratios,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_earnings_dates(ticker: str) -> Any:
                return _serialize(self.market_data.earnings_dates(ticker.upper().strip()))

            tools.append(
                make_tool(
                    name="earnings_dates",
                    description="Fetch upcoming earnings dates and recent surprise history.",
                    input_model=schemas.EarningsDatesInput,
                    handler=handle_earnings_dates,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

        # ---------------------------------------------------------------------
        # Data Tools: Risk Analyst
        # ---------------------------------------------------------------------
        if role == "risk_analyst":
            def handle_portfolio_risk() -> dict[str, Any]:
                account = self.broker_reader.get_account()
                positions = self.broker_reader.get_positions()
                equity = float(getattr(account, "equity", 0))
                cash = float(getattr(account, "cash", 0))

                pos_summaries = []
                total_market_val = 0.0
                sector_exp: dict[str, float] = {}

                for pos in positions:
                    sym = (
                        getattr(pos, "symbol", "")
                        if hasattr(pos, "symbol")
                        else pos.get("symbol", "")
                    )
                    mv = getattr(pos, "market_value", None)
                    if mv is None:
                        qty = float(getattr(pos, "quantity", 0))
                        price = float(
                            getattr(pos, "current_price", 0)
                            or getattr(pos, "average_entry_price", 0)
                        )
                        mv = qty * price
                    else:
                        mv = float(mv)
                    total_market_val += mv
                    concentration = (mv / equity) if equity > 0 else 0.0

                    # Sector lookup
                    row = self.db.connection.execute(
                        "SELECT sector FROM securities WHERE UPPER(symbol) = UPPER(?)", (sym,)
                    ).fetchone()
                    sec = row["sector"] if row and row["sector"] else "Unknown"
                    sector_exp[sec] = sector_exp.get(sec, 0.0) + mv

                    pos_summaries.append({
                        "symbol": sym,
                        "market_value": mv,
                        "concentration": concentration,
                        "sector": sec,
                    })

                # US 85: Open risk & portfolio correlation
                symbols = [p["symbol"] for p in pos_summaries if p.get("symbol")]
                open_risk = 0.0
                for pos in positions:
                    psym = (
                        getattr(pos, "symbol", "")
                        if hasattr(pos, "symbol")
                        else pos.get("symbol", "")
                    )
                    pqty = float(getattr(pos, "quantity", 0) or getattr(pos, "qty", 0))
                    pentry = float(
                        getattr(pos, "average_entry_price", 0)
                        or getattr(pos, "entry_price", 0)
                    )
                    order_row = self.db.connection.execute(
                        "SELECT draft_json FROM orders WHERE ticker = ? AND side = 'buy' "
                        "AND status IN ('submitted', 'approved', 'open') "
                        "ORDER BY id DESC LIMIT 1",
                        (psym,),
                    ).fetchone()
                    if order_row and order_row["draft_json"]:
                        try:
                            dj = json.loads(order_row["draft_json"])
                            if dj.get("stop"):
                                spx = float(dj["stop"])
                                if pentry > spx:
                                    open_risk += (pentry - spx) * pqty
                        except Exception:
                            pass

                # Compute pairwise correlation between returns of open position symbols
                corrs: dict[str, dict[str, float]] = {s: {} for s in symbols}
                returns_by_sym: dict[str, list[float]] = {}
                for s in symbols:
                    try:
                        bars = self.market_data.ohlcv(s, interval="1d", limit=30)
                        if bars and len(bars) >= 2:
                            closes = [float(b.get("c", b.get("close", 0))) for b in bars]
                            rets = [
                                (closes[i] - closes[i - 1]) / closes[i - 1]
                                for i in range(1, len(closes))
                                if closes[i - 1] > 0
                            ]
                            returns_by_sym[s] = rets
                    except Exception:
                        pass

                for s1 in symbols:
                    for s2 in symbols:
                        if s1 == s2:
                            corrs[s1][s2] = 1.0
                        elif s2 in corrs and s1 in corrs[s2]:
                            corrs[s1][s2] = corrs[s2][s1]
                        else:
                            r1 = returns_by_sym.get(s1, [])
                            r2 = returns_by_sym.get(s2, [])
                            n = min(len(r1), len(r2))
                            if n >= 2:
                                x = r1[-n:]
                                y = r2[-n:]
                                mx = sum(x) / n
                                my = sum(y) / n
                                num = sum(
                                    (xi - mx) * (yi - my)
                                    for xi, yi in zip(x, y, strict=False)
                                )
                                dx = sum((xi - mx) ** 2 for xi in x)
                                dy = sum((yi - my) ** 2 for yi in y)
                                val = num / ((dx * dy) ** 0.5) if dx > 0 and dy > 0 else 0.0
                                corrs[s1][s2] = round(max(-1.0, min(1.0, val)), 4)
                            else:
                                corrs[s1][s2] = 0.0

                return {
                    "equity": equity,
                    "cash": cash,
                    "cash_reserve_fraction": (cash / equity) if equity > 0 else 0.0,
                    "total_exposure": total_market_val,
                    "open_positions_count": len(positions),
                    "open_risk": round(open_risk, 2),
                    "positions": pos_summaries,
                    "sector_exposures": sector_exp,
                    "correlations": corrs,
                }

            tools.append(
                make_tool(
                    name="portfolio_risk",
                    description=(
                        "Analyze portfolio risks: exposures, concentration, "
                        "open risk, and correlations (US 85)."
                    ),
                    input_model=schemas.PortfolioRiskInput,
                    handler=handle_portfolio_risk,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_current_draft(ticker: str) -> dict[str, Any]:
                sym = ticker.upper().strip()
                state = self._get_or_create_ticker_state(sym)
                self._recompute_draft_if_possible(sym, state)
                return {"ticker": sym, "draft": state.get("draft")}

            tools.append(
                make_tool(
                    name="current_draft",
                    description="Inspect the current calculated order draft for a ticker.",
                    input_model=schemas.CurrentDraftInput,
                    handler=handle_current_draft,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

        # ---------------------------------------------------------------------
        # Portfolio Manager (PM) Only Tools
        # ---------------------------------------------------------------------
        if role == "pm":
            def handle_decide_proposal(proposal_id: int, action: str, reason: str, when: str | None = None) -> dict[str, Any]:
                row = self.db.connection.execute("SELECT cycle_id FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
                if action == "accept" and (cycle_id is None or not row or row["cycle_id"] != cycle_id):
                    raise ValueError("Accept requires the proposal's active supervised cycle")
                return self.decide_proposal(proposal_id, action, reason, when, agent_name)

            def handle_read_proposals(status: str | None = "pending", ticker: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
                query = "SELECT * FROM proposals WHERE (? IS NULL OR status=?) AND (? IS NULL OR ticker=?) ORDER BY id DESC LIMIT ?"
                ticker = ticker.upper().strip() if ticker else None
                rows = self.db.connection.execute(query, (status, status, ticker, ticker, min(max(limit, 1), 500))).fetchall()
                return [dict(row) for row in rows]

            tools.append(make_tool(name="read_proposals", description="Read open portfolio proposals.",
                                   input_model=schemas.ReadProposalsInput, handler=handle_read_proposals,
                                   agent_name=agent_name, chat_id=chat_id))
            tools.append(make_tool(name="decide_proposal", description="Decide a pending ticker proposal.",
                                   input_model=schemas.DecideProposalInput, handler=handle_decide_proposal,
                                   agent_name=agent_name, chat_id=chat_id))

            def handle_read_draft(ticker: str) -> dict[str, Any]:
                sym = ticker.upper().strip()
                state = self._get_or_create_ticker_state(sym)
                self._recompute_draft_if_possible(sym, state)
                return {"ticker": sym, "draft": state.get("draft")}

            tools.append(
                make_tool(
                    name="read_draft",
                    description="Read the current computed order draft for a ticker.",
                    input_model=schemas.ReadDraftInput,
                    handler=handle_read_draft,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_schedule_next_check(
                ticker: str, when: str, note: str = ""
            ) -> dict[str, Any]:
                sym = ticker.upper().strip()
                try:
                    requested_dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
                except Exception as exc:
                    raise ValueError(f"Invalid ISO datetime format for 'when': {when}") from exc

                if requested_dt.tzinfo is None:
                    requested_dt = requested_dt.replace(tzinfo=UTC)

                clamped_dt = clamp_schedule_date(
                    requested=requested_dt,
                    now=self.get_now(),
                    min_trading_days=self.min_trading_days,
                    max_trading_days=self.max_trading_days,
                    calendar=self.calendar,
                )
                clamped_iso = clamped_dt.isoformat().replace("+00:00", "Z")
                task_id = self.db.enqueue_scheduled_task(
                    agent=agent_name,
                    chat=sym,
                    when_ts=clamped_iso,
                    source="agent",
                    reason=note.strip() or f"Next check on {sym}",
                    data={"ticker": sym},
                )
                return {
                    "status": "scheduled",
                    "task_id": task_id,
                    "ticker": sym,
                    "when": clamped_iso,
                    "note": note,
                }

            tools.append(
                make_tool(
                    name="schedule_next_check",
                    description=(
                        "Schedule the mandatory future check task on a ticker before deciding."
                    ),
                    input_model=schemas.ScheduleNextCheckInput,
                    handler=handle_schedule_next_check,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_accept_order(ticker: str, action: str, reason: str) -> dict[str, Any]:
                sym = ticker.upper().strip()
                act = action.lower().strip()
                if act not in ("buy", "sell"):
                    raise ValueError(f"Invalid action: {action}. Must be 'buy' or 'sell'")

                # PM decision requires a future scheduled task
                if not self._has_future_scheduled_task(sym):
                    raise ValueError(
                        f"PM decision on {sym} requires a future scheduled task. "
                        "Call schedule_next_check first."
                    )

                if act == "sell":
                    positions = self.broker_reader.get_positions()
                    matching = any(
                        (
                            getattr(p, "symbol", "")
                            if hasattr(p, "symbol")
                            else p.get("symbol", "")
                        ).upper()
                        == sym
                        for p in positions
                    )
                    if not matching:
                        raise ValueError(
                            f"Cannot accept sell order: no open position found for {sym}"
                        )

                state = self._get_or_create_ticker_state(sym)
                state["decision"] = {
                    "action": act,
                    "reason": reason.strip(),
                    "decided_ts": self._now_iso(),
                    "status": "accepted",
                }
                self.db.set_ticker_state(sym, state, updated_ts=self._now_iso())

                # Notify callback (records intent, does NOT talk to broker)
                if self.on_accept is not None:
                    self.on_accept(sym, act, reason.strip())

                return {
                    "status": "accepted",
                    "ticker": sym,
                    "action": act,
                    "reason": reason.strip(),
                    "draft": state.get("draft"),
                }

            tools.append(
                make_tool(
                    name="accept_order",
                    description=(
                        "Accept an order draft for execution (records decision and intent; "
                        "requires a future scheduled check task; does not submit orders to broker)."
                    ),
                    input_model=schemas.AcceptOrderInput,
                    handler=handle_accept_order,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_defer(ticker: str, reason: str) -> dict[str, Any]:
                sym = ticker.upper().strip()

                # PM decision requires a future scheduled task
                if not self._has_future_scheduled_task(sym):
                    raise ValueError(
                        f"PM decision on {sym} requires a future scheduled task. "
                        "Call schedule_next_check first."
                    )

                state = self._get_or_create_ticker_state(sym)
                state["decision"] = {
                    "action": "defer",
                    "reason": reason.strip(),
                    "decided_ts": self._now_iso(),
                    "status": "deferred",
                }
                self.db.set_ticker_state(sym, state, updated_ts=self._now_iso())
                return {"status": "deferred", "ticker": sym, "reason": reason.strip()}

            tools.append(
                make_tool(
                    name="defer",
                    description=(
                        "Defer decision on a ticker to the next scheduled check "
                        "(requires a future scheduled check task)."
                    ),
                    input_model=schemas.DeferInput,
                    handler=handle_defer,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_watchlist_get() -> list[dict[str, Any]]:
                return self.db.list_watchlist()

            tools.append(
                make_tool(
                    name="watchlist_get",
                    description="Read current watchlist tickers.",
                    input_model=schemas.WatchlistGetInput,
                    handler=handle_watchlist_get,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

            def handle_watchlist_set(
                action: str = "add",
                ticker: str | None = None,
                tickers: list[str] | None = None,
                note: str = "",
            ) -> list[dict[str, Any]]:
                act = action.lower().strip()
                syms = []
                if ticker:
                    syms.append(ticker.upper().strip())
                if tickers:
                    syms.extend([t.upper().strip() for t in tickers if t.strip()])

                if act == "add":
                    for sym in syms:
                        self.db.add_watchlist(sym, note=note, added_ts=self._now_iso(), added_by=agent_name)
                elif act == "remove":
                    for sym in syms:
                        self.db.remove_watchlist(sym)
                elif act == "set":
                    # clear and reset
                    current = self.db.list_watchlist()
                    for item in current:
                        self.db.remove_watchlist(item["ticker"])
                    for sym in syms:
                        self.db.add_watchlist(sym, note=note, added_ts=self._now_iso(), added_by=agent_name)
                else:
                    raise ValueError(f"Invalid watchlist action: {action}")

                return self.db.list_watchlist()

            tools.append(
                make_tool(
                    name="watchlist_set",
                    description="Add, remove, or set tickers in the watchlist.",
                    input_model=schemas.WatchlistSetInput,
                    handler=handle_watchlist_set,
                    agent_name=agent_name,
                    chat_id=chat_id,
                )
            )

        return tools
