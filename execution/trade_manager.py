"""Trade manager: lifecycle of a Trade from entry to exit with events, exit reason, and trailing
stop."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Literal

from execution.order_flow import BracketBroker
from execution.trailing import (
    DEFAULT_K_TRAIL,
    DEFAULT_K_TRAIL_ACT,
    TrailingResult,
    TrailingState,
    next_trailing_stop,
)
from storage.office_db import OfficeDB, utc_now_iso

ExitReason = Literal["tp", "sl", "pm_sell", "expired"]


class TradeManager:
    """Tracks Trade lifecycle from entry to exit, managing events and trailing stop adjustments."""

    def __init__(
        self,
        db: OfficeDB,
        broker: BracketBroker,
        event_log: Any = None,
    ) -> None:
        self.db = db
        self.broker = broker
        self.event_log = event_log
        self._trailing_states: dict[str, TrailingState] = {}
        self._trade_ids: dict[str, int] = {}
        self._trade_orders: dict[str, int] = {}
        self._load_open_trades()

    def _load_open_trades(self) -> None:
        """Restore trailing state from DB for any open trades on startup."""
        rows = self.db.connection.execute(
            "SELECT * FROM trades WHERE closed_ts IS NULL ORDER BY id ASC"
        ).fetchall()
        for row in rows:
            ticker = row["ticker"]
            trade_id = int(row["id"])
            order_id = int(row["entry_order_id"])
            self._trade_ids[ticker] = trade_id
            self._trade_orders[ticker] = order_id

            # Recover state from order draft or events
            order = self.db.get_order(order_id)
            entry_price = Decimal(str(row["entry_price"]))
            atr = Decimal("1.0")
            k_trail_act = DEFAULT_K_TRAIL_ACT
            k_trail = DEFAULT_K_TRAIL
            stop = entry_price - Decimal("2.0") * atr

            if order and order.get("draft_json"):
                try:
                    d = json.loads(order["draft_json"])
                    if d.get("stop"):
                        stop = Decimal(str(d["stop"]))
                    if d.get("atr"):
                        atr = Decimal(str(d["atr"]))
                except Exception:
                    pass

            events = json.loads(row["events_json"]) if row["events_json"] else []
            highest = entry_price
            active = False
            for ev in events:
                if ev.get("atr"):
                    atr = Decimal(str(ev["atr"]))
                if ev.get("k_trail_act"):
                    k_trail_act = Decimal(str(ev["k_trail_act"]))
                if ev.get("k_trail"):
                    k_trail = Decimal(str(ev["k_trail"]))
                if ev.get("price") and Decimal(str(ev["price"])) > highest:
                    highest = Decimal(str(ev["price"]))
                if ev.get("new_stop"):
                    stop = Decimal(str(ev["new_stop"]))
                if ev.get("active"):
                    active = bool(ev["active"])

            self._trailing_states[ticker] = TrailingState(
                entry=entry_price,
                atr=atr,
                k_trail_act=k_trail_act,
                k_trail=k_trail,
                active=active,
                highest=highest,
                stop=stop,
            )

    def record_entry_fill(
        self,
        order_id: int | None = None,
        fill_price: Decimal | float | int | str | None = None,
        qty: Decimal | float | int | str = 0,
        atr: Decimal | float | int | str | None = None,
        k_trail_act: Decimal | float | int | str | None = None,
        k_trail: Decimal | float | int | str | None = None,
        stop_loss: Decimal | float | int | str | None = None,
        ts: str | None = None,
        entry_order_id: int | None = None,
        entry_price: Decimal | float | int | str | None = None,
        opened_ts: str | None = None,
        ticker: str | None = None,
    ) -> int:
        """Record entry fill for an order, opening a Trade and initiating trailing stop
        monitoring."""
        oid = order_id if order_id is not None else entry_order_id
        if oid is None:
            raise ValueError("order_id or entry_order_id is required")
        px = fill_price if fill_price is not None else entry_price
        if px is None:
            raise ValueError("fill_price or entry_price is required")

        order = self.db.get_order(oid)
        if not order:
            raise KeyError(f"Order {oid} not found in database")

        resolved_ticker = (ticker or order["ticker"]).upper()
        now_ts = ts or opened_ts or utc_now_iso()
        price_dec = Decimal(str(px))
        qty_dec = Decimal(str(qty))

        # Extract draft defaults if not supplied
        atr_dec = Decimal(str(atr)) if atr is not None else None
        stop_dec = Decimal(str(stop_loss)) if stop_loss is not None else None
        if order.get("draft_json"):
            try:
                draft_dict = json.loads(order["draft_json"])
                if atr_dec is None and draft_dict.get("atr"):
                    atr_dec = Decimal(str(draft_dict["atr"]))
                if stop_dec is None and draft_dict.get("stop"):
                    stop_dec = Decimal(str(draft_dict["stop"]))
            except Exception:
                pass

        if atr_dec is None:
            atr_dec = Decimal("1.0")
        if stop_dec is None:
            stop_dec = price_dec - (Decimal("2.0") * atr_dec)

        k_act_dec = Decimal(str(k_trail_act)) if k_trail_act is not None else DEFAULT_K_TRAIL_ACT
        k_t_dec = Decimal(str(k_trail)) if k_trail is not None else DEFAULT_K_TRAIL

        initial_events = [
            {
                "ts": now_ts,
                "event": "entry_filled",
                "price": float(price_dec),
                "qty": float(qty_dec),
                "atr": float(atr_dec),
                "k_trail_act": float(k_act_dec),
                "k_trail": float(k_t_dec),
                "stop": float(stop_dec),
            }
        ]

        trade_id = self.db.insert_trade(
            ticker=resolved_ticker,
            entry_order_id=oid,
            entry_price=float(price_dec),
            qty=float(qty_dec),
            opened_ts=now_ts,
            events=initial_events,
        )

        state = TrailingState(
            entry=price_dec,
            atr=atr_dec,
            k_trail_act=k_act_dec,
            k_trail=k_t_dec,
            active=False,
            highest=price_dec,
            stop=stop_dec,
        )

        self._trailing_states[resolved_ticker] = state
        self._trade_ids[resolved_ticker] = trade_id
        self._trade_orders[resolved_ticker] = oid

        # Update order status & events
        self.db.update_order_status(oid, status="filled")
        self.db.insert_order_event(
            oid,
            "filled",
            {"price": str(price_dec), "qty": str(qty_dec)},
            ts=now_ts,
        )
        self.db.add_inbox(
            "order_executed",
            f"Order {oid} filled for {resolved_ticker}: {qty_dec} @ {price_dec}",
            ts=now_ts,
        )

        if self.event_log is not None:
            self.event_log.append(
                type="trade.opened",
                subject=f"trade:{trade_id}",
                payload={
                    "trade_id": trade_id,
                    "ticker": resolved_ticker,
                    "entry_order_id": oid,
                    "entry_price": float(price_dec),
                    "qty": float(qty_dec),
                    "opened_ts": now_ts,
                },
                actor="trade_manager",
            )

        return trade_id

    def record_exit_fill(
        self,
        trade_id: int | None = None,
        exit_price: Decimal | float | int | str = 0,
        exit_reason: ExitReason = "tp",
        ts: str | None = None,
        ticker: str | None = None,
        closed_ts: str | None = None,
        exit_order_id: int | None = None,
    ) -> None:
        """Record exit fill for an open Trade, closing it with specified exit reason."""
        if exit_reason not in ("tp", "sl", "pm_sell", "expired"):
            raise ValueError(f"Invalid exit reason: {exit_reason}")

        tid = trade_id
        if tid is None and ticker:
            tid = self._trade_ids.get(ticker.upper())
            if tid is None:
                row = self.db.connection.execute(
                    "SELECT id FROM trades WHERE ticker = ? AND closed_ts IS NULL ORDER BY id DESC LIMIT 1",
                    (ticker.upper(),),
                ).fetchone()
                if row:
                    tid = int(row["id"])

        if tid is None:
            raise ValueError("trade_id or active ticker is required")

        trade = self.db.get_trade(tid)
        if not trade:
            raise KeyError(f"Trade {trade_id} not found")

        now_ts = ts or utc_now_iso()
        price_dec = Decimal(str(exit_price))

        events: list[dict[str, Any]] = (
            json.loads(trade["events_json"]) if trade["events_json"] else []
        )
        events.append(
            {
                "ts": now_ts,
                "event": f"exit_{exit_reason}",
                "price": float(price_dec),
                "reason": exit_reason,
            }
        )

        self.db.close_trade(
            trade_id=tid,
            exit_price=float(price_dec),
            exit_reason=exit_reason,
            closed_ts=now_ts,
            events=events,
        )

        ticker = trade["ticker"]
        self._trailing_states.pop(ticker, None)
        self._trade_ids.pop(ticker, None)
        self._trade_orders.pop(ticker, None)

        self.db.add_inbox(
            "order_executed",
            f"Trade {tid} on {ticker} closed via {exit_reason} at {price_dec}",
            ts=now_ts,
        )

        if self.event_log is not None:
            self.event_log.append(
                type="trade.closed",
                subject=f"trade:{tid}",
                payload={
                    "trade_id": tid,
                    "ticker": ticker,
                    "exit_price": float(price_dec),
                    "exit_reason": exit_reason,
                    "closed_ts": now_ts,
                },
                actor="trade_manager",
            )

    def on_price(
        self,
        ticker: str,
        price: Decimal | float | int | str,
        atr_at_entry: Decimal | float | int | str | None = None,
    ) -> TrailingResult | None:
        """Process incoming price observation for a ticker and update trailing stop
        deterministically.

        When the stop changes, calls broker.modify_stop and records a trailing event.
        No LLM involved.
        """
        sym = ticker.upper()
        state = self._trailing_states.get(sym)
        if state is None:
            # Check if there is an open trade in DB
            self._load_open_trades()
            state = self._trailing_states.get(sym)
            if state is None:
                return None

        price_dec = Decimal(str(price))
        res = next_trailing_stop(state, price_dec, atr_at_entry=atr_at_entry)
        self._trailing_states[sym] = res.state

        if res.stop_changed:
            trade_id = self._trade_ids.get(sym)
            order_id = self._trade_orders.get(sym)

            # Modify stop on broker order
            if order_id is not None:
                order = self.db.get_order(order_id)
                if order and order.get("broker_order_id"):
                    self.broker.modify_stop(order["broker_order_id"], res.state.stop)

                self.db.insert_order_event(
                    order_id,
                    "modify_stop",
                    {"new_stop": str(res.state.stop), "price": str(price_dec)},
                )

            # Append event to trade in DB
            if trade_id is not None:
                trade = self.db.get_trade(trade_id)
                if trade:
                    events = json.loads(trade["events_json"]) if trade["events_json"] else []
                    events.append(
                        {
                            "ts": utc_now_iso(),
                            "event": "trailing_stop_updated",
                            "price": float(price_dec),
                            "new_stop": float(res.state.stop),
                            "active": res.state.active,
                        }
                    )
                    self.db.connection.execute(
                        "UPDATE trades SET events_json = ? WHERE id = ?",
                        (json.dumps(events), trade_id),
                    )

        return res

    def get_open_trade(self, ticker: str) -> dict | None:
        """Get currently open trade for a ticker."""
        row = self.db.connection.execute(
            "SELECT * FROM trades WHERE ticker = ? AND closed_ts IS NULL ORDER BY id DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
        return dict(row) if row else None

    def get_trade(self, trade_id: int) -> dict | None:
        """Get trade by ID."""
        return self.db.get_trade(trade_id)

    def list_trades(
        self, ticker: str | None = None, open_only: bool = False
    ) -> list[dict]:
        """List trades, optionally filtered by ticker and open status."""
        query = "SELECT * FROM trades WHERE 1=1"
        params: list[Any] = []
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker.upper())
        if open_only:
            query += " AND closed_ts IS NULL"
        query += " ORDER BY id ASC"
        rows = self.db.connection.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_trailing_state(self, ticker: str) -> TrailingState | None:
        """Get active trailing state for a ticker."""
        return self._trailing_states.get(ticker.upper())
