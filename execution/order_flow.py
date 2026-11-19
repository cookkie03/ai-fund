"""Order flow execution: Risk Gate, approval queue, serialized submission, idempotency, and halt."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable

from execution.order_draft import OrderDraft
from execution.risk_gate import (
    GateOrder,
    RiskGateContext,
    RiskGateResult,
    run_risk_gate,
)
from storage.office_db import OfficeDB, utc_now_iso

logger = logging.getLogger(__name__)


@runtime_checkable
class BracketBroker(Protocol):
    """Protocol for bracket order execution with the broker."""

    def submit_bracket(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        limit_price: Decimal,
        take_profit: Decimal,
        stop_loss: Decimal,
    ) -> str:
        """Submit a bracket order and return the broker order ID."""
        ...

    def modify_stop(self, broker_order_id: str, stop: Decimal) -> None:
        """Modify stop loss price on an active bracket order."""
        ...

    def modify_take_profit(self, broker_order_id: str, take_profit: Decimal) -> None:
        """Modify take profit price on an active bracket order."""
        ...

    def cancel(self, broker_order_id: str) -> None:
        """Cancel an open order by broker order ID."""
        ...

    def find_by_client_id(self, client_order_id: str) -> Any | None:
        """Find an order by client order ID (reconciliation / idempotency)."""
        ...

    def get_order(self, broker_order_id: str) -> Any | None:
        """Get order status/details by broker order ID."""
        ...

    def get_open_orders(self, symbol: str | None = None) -> list[Any]:
        """Get open orders, optionally filtered by symbol."""
        ...

    def is_market_open(self) -> bool:
        """Check if market is currently open for trading."""
        ...


class SystemHalt:
    """Manages system halt state stored durably in OfficeDB."""

    def __init__(self, db: OfficeDB, broker: BracketBroker | None = None) -> None:
        self._db = db
        self._broker = broker
        self._init_db()

    def _init_db(self) -> None:
        with self._db.transaction():
            self._db.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_ts TEXT NOT NULL
                )
                """
            )

    def is_halted(self) -> bool:
        row = self._db.connection.execute(
            "SELECT value FROM system_state WHERE key = 'halted'"
        ).fetchone()
        if not row:
            return False
        return row["value"] == "1"

    def __call__(self, cancel_open: bool = True) -> None:
        """Allow halt(cancel_open=True) directly on the Halt instance."""
        self.halt(cancel_open=cancel_open)

    def halt(self, cancel_open: bool = True) -> None:
        ts = utc_now_iso()
        with self._db.transaction():
            self._db.connection.execute(
                """
                INSERT INTO system_state (key, value, updated_ts)
                VALUES ('halted', '1', ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_ts = excluded.updated_ts
                """,
                (ts,),
            )
            self._db.add_inbox("halt", "System halted: trading stopped", ts=ts)

        if cancel_open and self._broker is not None:
            # Cancel open orders
            rows = self._db.connection.execute(
                """
                SELECT id, broker_order_id, client_order_id, status
                FROM orders
                WHERE status IN ('submitted', 'open', 'queued')
                """
            ).fetchall()
            for row in rows:
                order_id = row["id"]
                b_id = row["broker_order_id"]
                if b_id:
                    try:
                        self._broker.cancel(b_id)
                    except Exception:
                        pass
                self._db.update_order_status(order_id, status="cancelled")
                self._db.insert_order_event(
                    order_id,
                    "cancelled",
                    {"reason": "System halt"},
                    ts=ts,
                )

    def resume(self) -> None:
        ts = utc_now_iso()
        with self._db.transaction():
            self._db.connection.execute(
                """
                INSERT INTO system_state (key, value, updated_ts)
                VALUES ('halted', '0', ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_ts = excluded.updated_ts
                """,
                (ts,),
            )
            self._db.add_inbox("resume", "System resumed: trading allowed", ts=ts)


@dataclass(frozen=True)
class Outcome:
    """Outcome of order processing, approval, or cancellation."""

    status: str  # "submitted", "pending", "queued", "deferred", "rejected", "expired"
    reasons: tuple[str, ...] = ()
    order_id: int | None = None
    client_order_id: str | None = None
    broker_order_id: str | None = None
    action: str = ""

    @property
    def is_deferred(self) -> bool:
        return self.status == "deferred"

    @property
    def is_submitted(self) -> bool:
        return self.status == "submitted"

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    @property
    def is_queued(self) -> bool:
        return self.status == "queued"


def _draft_to_dict(draft: OrderDraft) -> dict[str, Any]:
    return {
        "symbol": draft.symbol,
        "side": draft.side,
        "entry": str(draft.entry),
        "stop": str(draft.stop) if draft.stop is not None else None,
        "take_profit": str(draft.take_profit) if draft.take_profit is not None else None,
        "quantity": str(draft.quantity),
        "risk_reward": str(draft.risk_reward) if draft.risk_reward is not None else None,
        "risk_amount": str(draft.risk_amount) if draft.risk_amount is not None else None,
        "notional": str(draft.notional),
    }


def _draft_from_dict(d: dict[str, Any]) -> OrderDraft:
    return OrderDraft(
        symbol=d["symbol"],
        side=d["side"],
        entry=Decimal(str(d["entry"])),
        stop=Decimal(str(d["stop"])) if d.get("stop") is not None else None,
        take_profit=Decimal(str(d["take_profit"])) if d.get("take_profit") is not None else None,
        quantity=Decimal(str(d["quantity"])),
        risk_reward=Decimal(str(d["risk_reward"])) if d.get("risk_reward") is not None else None,
        risk_amount=Decimal(str(d["risk_amount"])) if d.get("risk_amount") is not None else None,
        notional=Decimal(str(d["notional"])),
    )


class OrderFlow:
    """Coordinates accepted order processing, risk gating, approval, and broker submission."""

    def __init__(
        self,
        db: OfficeDB,
        broker: BracketBroker,
        halt: SystemHalt | None = None,
        approval_mode: Literal["auto", "manual"] = "auto",
        is_market_open: Callable[[], bool] | None = None,
    ) -> None:
        self.db = db
        self.broker = broker
        self.halt = halt or SystemHalt(db, broker)
        self.approval_mode: Literal["auto", "manual"] = approval_mode
        self._is_market_open_fn = is_market_open
        self._lock = threading.RLock()

    def is_market_open(self) -> bool:
        if self._is_market_open_fn is not None:
            return bool(self._is_market_open_fn())
        if hasattr(self.broker, "is_market_open"):
            return bool(self.broker.is_market_open())
        return True

    def process_accepted_order(
        self,
        ticker: str,
        action: str,
        draft: OrderDraft,
        ctx: RiskGateContext,
        client_order_id: str | None = None,
    ) -> Outcome:
        """Process PM-accepted order through Risk Gate, approval queue, and serialized send.

        Returns Outcome (e.g. deferred with reasons, pending approval, queued, or submitted).
        """
        with self._lock:
            # 1. Check system halt
            if self.halt.is_halted():
                return Outcome(
                    status="deferred",
                    reasons=("System is halted: all order submissions blocked",),
                    action=action,
                )

            # 2. Build GateOrder for Risk Gate evaluation
            sector = ctx.sector_map.get(ticker.upper(), "")
            if draft.side == "buy":
                gate_order = GateOrder(
                    symbol=draft.symbol,
                    side="buy",
                    quantity=draft.quantity,
                    entry=draft.entry,
                    stop=draft.stop if draft.stop is not None else Decimal("1"),
                    take_profit=draft.take_profit
                    if draft.take_profit is not None
                    else Decimal("1"),
                    sector=sector,
                )
            else:
                # Sell on open position
                # stop and take_profit must be positive in GateOrder.__post_init__
                gate_order = GateOrder(
                    symbol=draft.symbol,
                    side="sell",
                    quantity=draft.quantity,
                    entry=draft.entry,
                    stop=draft.entry,
                    take_profit=draft.entry,
                    sector=sector,
                )

            # 3. Evaluate Risk Gate
            gate_res: RiskGateResult = run_risk_gate(gate_order, ctx)
            if not gate_res.allowed:
                return Outcome(
                    status="deferred",
                    reasons=gate_res.reasons,
                    action=action,
                )

            # 4. Determine client_order_id
            cid = client_order_id or (
                f"ord-{ticker.lower()}-{draft.side}-{draft.draft_hash[:8]}-{uuid.uuid4().hex[:6]}"
            )

            # 5. Check if order with this client_order_id already exists in DB (idempotency)
            existing_db = self.db.get_order_by_client_id(cid)
            draft_dict = _draft_to_dict(draft)

            if existing_db is not None:
                order_id = int(existing_db["id"])
                # If already submitted or terminal, submit/reconcile directly
                return self._submit_order_locked(order_id, ticker, draft, cid, action)

            # 6. Approval Queue
            if self.approval_mode == "manual":
                order_id = self.db.insert_order(
                    ticker=ticker.upper(),
                    side=draft.side,
                    draft=draft_dict,
                    draft_hash=draft.draft_hash,
                    approval_status="pending",
                    client_order_id=cid,
                    status="pending",
                )
                self.db.insert_order_event(
                    order_id,
                    "created",
                    {"approval_status": "pending", "draft_hash": draft.draft_hash},
                )
                return Outcome(
                    status="pending",
                    order_id=order_id,
                    client_order_id=cid,
                    action=action,
                )

            # Mode 'auto': store and send immediately
            order_id = self.db.insert_order(
                ticker=ticker.upper(),
                side=draft.side,
                draft=draft_dict,
                draft_hash=draft.draft_hash,
                approval_status="auto",
                client_order_id=cid,
                status="pending",
            )
            self.db.insert_order_event(
                order_id,
                "created",
                {"approval_status": "auto", "draft_hash": draft.draft_hash},
            )

            return self._submit_order_locked(order_id, ticker, draft, cid, action)

    def _submit_order_locked(
        self,
        order_id: int,
        ticker: str,
        draft: OrderDraft,
        client_order_id: str,
        action: str,
    ) -> Outcome:
        """Internal submission method, must be called with self._lock held."""
        # 1. Re-check halt
        if self.halt.is_halted():
            self.db.update_order_status(order_id, status="deferred")
            self.db.insert_order_event(
                order_id, "blocked", {"reason": "System is halted"}
            )
            return Outcome(
                status="deferred",
                order_id=order_id,
                client_order_id=client_order_id,
                reasons=("System is halted",),
                action=action,
            )

        # 2. Check broker idempotency (find_by_client_id)
        existing = self.broker.find_by_client_id(client_order_id)
        if existing is not None:
            broker_order_id = getattr(
                existing,
                "broker_order_id",
                getattr(existing, "id", str(existing)),
            )
            status = getattr(existing, "status", "submitted")
            self.db.update_order_status(
                order_id, status=status, broker_order_id=broker_order_id
            )
            self.db.insert_order_event(
                order_id, "reconciled", {"broker_order_id": broker_order_id, "status": status}
            )
            return Outcome(
                status="submitted",
                order_id=order_id,
                client_order_id=client_order_id,
                broker_order_id=broker_order_id,
                action=action,
            )

        # 3. Market Open check: only bracket limit orders when market open
        if not self.is_market_open():
            self.db.update_order_status(order_id, status="queued")
            self.db.insert_order_event(order_id, "queued", {"reason": "Market closed"})
            return Outcome(
                status="queued",
                order_id=order_id,
                client_order_id=client_order_id,
                action=action,
            )

        # 4. Handle Sell vs Buy
        if draft.side == "sell":
            # "Sell on an open position: moves the TP of the open bracket to the sell limit price
            # keeping SL."
            open_broker_order_id = self._find_open_bracket_order_id(ticker)
            if open_broker_order_id:
                self.broker.modify_take_profit(open_broker_order_id, draft.limit_price)
                self.db.update_order_status(
                    order_id, status="submitted", broker_order_id=open_broker_order_id
                )
                self.db.insert_order_event(
                    order_id,
                    "tp_modified_for_sell",
                    {
                        "target_broker_order_id": open_broker_order_id,
                        "limit_price": str(draft.limit_price),
                    },
                )
                return Outcome(
                    status="submitted",
                    order_id=order_id,
                    client_order_id=client_order_id,
                    broker_order_id=open_broker_order_id,
                    action=action,
                )
            else:
                self.db.update_order_status(order_id, status="deferred")
                self.db.insert_order_event(
                    order_id,
                    "deferred",
                    {"reason": "No open bracket order found to modify take profit"},
                )
                return Outcome(
                    status="deferred",
                    order_id=order_id,
                    client_order_id=client_order_id,
                    reasons=("No open bracket order found to modify take profit for sell",),
                    action=action,
                )

        # 5. Buy: submit bracket limit order (never market)
        if draft.stop is None or draft.take_profit is None:
            raise ValueError("Buy bracket order requires non-null stop and take_profit")

        try:
            broker_order_id = self.broker.submit_bracket(
                client_order_id=client_order_id,
                symbol=draft.symbol,
                side=draft.side,
                qty=draft.quantity,
                limit_price=draft.limit_price,
                take_profit=draft.take_profit,
                stop_loss=draft.stop,
            )
        except Exception as exc:  # broker refused or unreachable: never leave the order pending
            logger.error("Broker rejected bracket order %s: %s", client_order_id, exc)
            self.db.update_order_status(order_id, status="rejected")
            self.db.insert_order_event(order_id, "broker_error", {"error": str(exc)})
            return Outcome(
                status="rejected",
                order_id=order_id,
                client_order_id=client_order_id,
                reasons=(f"Broker error: {exc}",),
                action=action,
            )
        self.db.update_order_status(
            order_id, status="submitted", broker_order_id=broker_order_id
        )
        self.db.insert_order_event(
            order_id, "submitted", {"broker_order_id": broker_order_id}
        )
        return Outcome(
            status="submitted",
            order_id=order_id,
            client_order_id=client_order_id,
            broker_order_id=broker_order_id,
            action=action,
        )

    _BROKER_STATUS_MAP = {
        "new": "submitted",
        "accepted": "submitted",
        "pending_new": "submitted",
        "submitted": "submitted",
        "open": "submitted",
        "partially_filled": "submitted",
        "filled": "filled",
        "canceled": "cancelled",
        "cancelled": "cancelled",
        "expired": "expired",
        "rejected": "rejected",
        "done_for_day": "cancelled",
    }

    def sync_broker_orders(self) -> list[int]:
        """Align local orders still marked submitted with the broker's current state.

        Returns the ids of orders whose status changed.
        """
        rows = self.db.connection.execute(
            "SELECT id, status, broker_order_id FROM orders "
            "WHERE status = 'submitted' AND broker_order_id IS NOT NULL"
        ).fetchall()
        changed: list[int] = []
        for row in rows:
            try:
                broker_order = self.broker.get_order(row["broker_order_id"])
            except Exception as exc:
                logger.warning("Order sync failed for %s: %s", row["broker_order_id"], exc)
                continue
            if broker_order is None:
                continue
            raw = getattr(broker_order, "status", None)
            raw = str(getattr(raw, "value", raw)).split(".")[-1].lower()
            new_status = self._BROKER_STATUS_MAP.get(raw)
            if new_status is None or new_status == row["status"]:
                continue
            self.db.update_order_status(row["id"], status=new_status)
            self.db.insert_order_event(
                row["id"],
                "reconciled",
                {"broker_order_id": row["broker_order_id"], "broker_status": raw},
            )
            changed.append(int(row["id"]))
        return changed

    def _find_open_bracket_order_id(self, ticker: str) -> str | None:
        """Find the broker order ID of the active bracket order for a ticker."""
        row = self.db.connection.execute(
            """
            SELECT broker_order_id FROM orders
            WHERE ticker = ? AND side = 'buy' AND broker_order_id IS NOT NULL
              AND status IN ('submitted', 'open', 'filled')
            ORDER BY id DESC LIMIT 1
            """,
            (ticker.upper(),),
        ).fetchone()
        if row and row["broker_order_id"]:
            return str(row["broker_order_id"])

        open_orders = self.broker.get_open_orders(ticker.upper())
        if open_orders:
            first = open_orders[0]
            return str(getattr(first, "broker_order_id", getattr(first, "id", "")))
        return None

    def approve(
        self,
        order_id: int,
        current_draft: OrderDraft | None = None,
        ctx: RiskGateContext | None = None,
    ) -> Outcome:
        """Approve a pending order.

        Approval fails if the draft hash changed.
        The Risk Gate is re-run on approval with fresh portfolio context.
        """
        with self._lock:
            order = self.db.get_order(order_id)
            if not order or order["approval_status"] != "pending":
                return Outcome(
                    status="deferred",
                    reasons=(f"Order {order_id} is not pending approval",),
                )

            # Check draft hash
            if current_draft is not None:
                if current_draft.draft_hash != order["draft_hash"]:
                    self.db.update_order_status(
                        order_id, status="rejected", approval_status="rejected"
                    )
                    self.db.insert_order_event(
                        order_id, "rejected", {"reason": "Draft hash changed"}
                    )
                    self.db.add_inbox(
                        "order_rejected",
                        f"Order {order['client_order_id']} approval failed: draft hash changed",
                    )
                    return Outcome(
                        status="deferred",
                        order_id=order_id,
                        reasons=("Draft hash changed",),
                    )

            # Reconstruct draft if needed
            draft = current_draft
            if draft is None:
                draft = _draft_from_dict(json.loads(order["draft_json"]))

            # Re-run Risk Gate if fresh context provided
            if ctx is not None:
                sector = ctx.sector_map.get(order["ticker"], "")
                if draft.side == "buy":
                    gate_order = GateOrder(
                        symbol=draft.symbol,
                        side="buy",
                        quantity=draft.quantity,
                        entry=draft.entry,
                        stop=draft.stop if draft.stop is not None else Decimal("1"),
                        take_profit=draft.take_profit
                        if draft.take_profit is not None
                        else Decimal("1"),
                        sector=sector,
                    )
                else:
                    gate_order = GateOrder(
                        symbol=draft.symbol,
                        side="sell",
                        quantity=draft.quantity,
                        entry=draft.entry,
                        stop=draft.entry,
                        take_profit=draft.entry,
                        sector=sector,
                    )

                gate_res = run_risk_gate(gate_order, ctx)
                if not gate_res.allowed:
                    self.db.update_order_status(
                        order_id, status="deferred", approval_status="rejected"
                    )
                    self.db.insert_order_event(
                        order_id,
                        "risk_gate_blocked",
                        {"reasons": list(gate_res.reasons)},
                    )
                    return Outcome(
                        status="deferred",
                        order_id=order_id,
                        reasons=gate_res.reasons,
                    )

            # Mark approved
            self.db.update_order_status(
                order_id, status="approved", approval_status="approved"
            )
            self.db.insert_order_event(order_id, "approved")

            return self._submit_order_locked(
                order_id, order["ticker"], draft, order["client_order_id"], order["side"]
            )

    def reject(self, order_id: int, reason: str = "") -> Outcome:
        """Reject a pending order in the approval queue."""
        with self._lock:
            order = self.db.get_order(order_id)
            if not order:
                return Outcome(
                    status="deferred", reasons=(f"Order {order_id} not found",)
                )

            ts = utc_now_iso()
            rej_reason = reason or "User rejected order"
            self.db.update_order_status(
                order_id, status="rejected", approval_status="rejected"
            )
            self.db.insert_order_event(order_id, "rejected", {"reason": rej_reason}, ts=ts)
            self.db.add_inbox(
                "order_rejected",
                f"Order {order['client_order_id']} rejected: {rej_reason}",
                ts=ts,
            )
            # US 62: Write Rimando with reason to PM chat so PM takes it into account
            pm_chat_id = self.db.get_or_create_chat("portfolio_manager", order["ticker"])
            self.db.append_message(
                chat_id=pm_chat_id,
                author="system",
                text=f"Rimando: ordine rifiutato. Motivo: {rej_reason}",
                kind="original",
                ts=ts,
            )
            return Outcome(
                status="deferred",
                order_id=order_id,
                reasons=(rej_reason,),
            )

    def expire_pending(self, now: str | None = None) -> list[int]:
        """Expire all pending orders at end of session as deferrals."""
        with self._lock:
            ts = now or utc_now_iso()
            rows = self.db.connection.execute(
                "SELECT id, ticker, client_order_id FROM orders WHERE approval_status = 'pending'"
            ).fetchall()
            expired_ids: list[int] = []
            for row in rows:
                oid = int(row["id"])
                cid = row["client_order_id"]
                ticker = row["ticker"]
                self.db.update_order_status(
                    oid, status="expired", approval_status="expired"
                )
                self.db.insert_order_event(
                    oid,
                    "expired",
                    {"reason": "Pending order expired at end of session"},
                    ts=ts,
                )
                self.db.add_inbox(
                    "order_expired",
                    f"Pending order {cid} for {ticker} expired at end of session",
                    ts=ts,
                )
                expired_ids.append(oid)
            return expired_ids

    def release_queued(self, now: str | None = None) -> list[Outcome]:
        """Release queued orders once market opens."""
        with self._lock:
            if not self.is_market_open():
                return []
            if self.halt.is_halted():
                return []

            rows = self.db.connection.execute(
                """
                SELECT id, ticker, side, draft_json, client_order_id
                FROM orders
                WHERE status = 'queued'
                ORDER BY id ASC
                """
            ).fetchall()

            outcomes: list[Outcome] = []
            for row in rows:
                order_id = int(row["id"])
                ticker = row["ticker"]
                cid = row["client_order_id"]
                side = row["side"]
                draft = _draft_from_dict(json.loads(row["draft_json"]))
                outcome = self._submit_order_locked(order_id, ticker, draft, cid, side)
                outcomes.append(outcome)
            return outcomes

    def cancel_entry_if_unfilled(self, ticker: str) -> bool:
        """Cancel unfilled entry order when next scheduled task runs on ticker."""
        with self._lock:
            ts = utc_now_iso()
            rows = self.db.connection.execute(
                """
                SELECT id, broker_order_id, client_order_id, status
                FROM orders
                WHERE ticker = ? AND side = 'buy'
                  AND status IN ('submitted', 'open', 'queued', 'pending')
                ORDER BY id DESC
                """,
                (ticker.upper(),),
            ).fetchall()

            cancelled_any = False
            for row in rows:
                oid = int(row["id"])
                b_id = row["broker_order_id"]
                cid = row["client_order_id"]

                if b_id:
                    broker_order = self.broker.get_order(b_id)
                    filled_qty = Decimal("0")
                    status = "open"
                    if broker_order is not None:
                        filled_qty = getattr(
                            broker_order,
                            "filled_quantity",
                            getattr(broker_order, "filled_qty", Decimal("0")),
                        )
                        status = getattr(broker_order, "status", "open")

                    if (
                        status not in ("filled", "cancelled", "expired")
                        and filled_qty == Decimal("0")
                    ):
                        try:
                            self.broker.cancel(b_id)
                        except Exception:
                            pass
                        self.db.update_order_status(oid, status="expired")
                        self.db.insert_order_event(
                            oid,
                            "expired",
                            {"reason": "Unfilled entry order cancelled at next scheduled task"},
                            ts=ts,
                        )
                        self.db.add_inbox(
                            "order_expired",
                            (
                                f"Unfilled entry order {cid} for {ticker} "
                                "expired at next scheduled task"
                            ),
                            ts=ts,
                        )
                        cancelled_any = True
                else:
                    self.db.update_order_status(oid, status="expired")
                    self.db.insert_order_event(
                        oid,
                        "expired",
                        {"reason": "Unfilled queued entry order cancelled at next scheduled task"},
                        ts=ts,
                    )
                    self.db.add_inbox(
                        "order_expired",
                        f"Unfilled entry order {cid} for {ticker} expired at next scheduled task",
                        ts=ts,
                    )
                    cancelled_any = True

            return cancelled_any

    def halt(self, cancel_open: bool = True) -> None:
        """Emergency stop: halts system and optionally cancels open orders."""
        with self._lock:
            self.halt.halt(cancel_open=cancel_open)

    def resume(self) -> None:
        """Resume trading after halt."""
        with self._lock:
            self.halt.resume()
