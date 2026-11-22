"""Uscite dalle posizioni decise dall'utente: chiusura totale/parziale e modifica di stop/target.

Passa dal flusso ordini esistente: Halt, ordine `sell` tracciato in `orders`, Risk Gate, broker.
Il Risk Gate può solo bloccare: una chiusura è bloccata se la quantità supera quella detenuta,
l'ampliamento di uno stop se il rischio per trade supera il limite attivo.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from execution.risk_gate import (
    GateOrder,
    RiskGateContext,
    guard_risk_per_trade,
    run_risk_gate,
)
from storage.office_db import OfficeDB

logger = logging.getLogger(__name__)

HALT_REASON = "System is halted: all order submissions blocked"


@dataclass(frozen=True)
class CloseResult:
    """Esito di `PositionCloser.close_position`."""

    broker_order_id: str
    status: str = "submitted"  # "filled" se eseguito subito, altrimenti il fill arriva dallo stream
    fill_price: Decimal | None = None
    filled_qty: Decimal | None = None
    residual_order_id: str | None = None  # nuovo ordine protettivo per la quantità residua


@runtime_checkable
class PositionCloser(Protocol):
    """Capacità opzionale del broker: vendere (parte di) una posizione protetta da bracket."""

    def close_position(
        self,
        *,
        client_order_id: str,
        symbol: str,
        qty: Decimal,
        order_type: str,
        limit_price: Decimal | None,
        bracket_order_id: str | None,
        residual_qty: Decimal,
        residual_stop: Decimal | None,
        residual_target: Decimal | None,
    ) -> CloseResult: ...


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def _remaining(trade: dict) -> Decimal:
    return _dec(trade["qty"]) - _dec(trade.get("closed_qty") or 0)


class PositionExits:
    def __init__(self, db: OfficeDB, broker: Any, halt: Any, trade_manager: Any,
                 event_log: Any = None) -> None:
        self.db = db
        self.broker = broker
        self.halt = halt
        self.trade_manager = trade_manager
        self.event_log = event_log

    # --- chiusura -------------------------------------------------------------------------

    def _gate_close(self, trade: dict, qty: Decimal, price: Decimal,
                    ctx: RiskGateContext) -> tuple[bool, list[str]]:
        ticker = trade["ticker"]
        remaining = _remaining(trade)
        gate_ctx = replace(
            ctx,
            halted=self.halt.is_halted(),
            position_quantities={**ctx.position_quantities, ticker: remaining},
        )
        order = GateOrder(symbol=ticker, side="sell", quantity=qty, entry=price, stop=price,
                          take_profit=price, sector=ctx.sector_map.get(ticker, ""))
        res = run_risk_gate(order, gate_ctx)
        return res.allowed, list(res.reasons)

    def preview_close(self, trade: dict, qty: Decimal | None, order_type: str,
                      limit_price: Decimal | None, price: Decimal,
                      ctx: RiskGateContext) -> dict[str, Any]:
        remaining = _remaining(trade)
        q = qty if qty is not None else remaining
        ref = limit_price if (order_type == "limit" and limit_price) else price
        entry = _dec(trade["entry_price"])
        allowed, reasons = self._gate_close(trade, q, ref, ctx) if q > 0 else (False, [
            "La quantità deve essere positiva"])
        if q > remaining:
            allowed, reasons = False, reasons or [
                f"Quantità {q} superiore alla residua {remaining}"
            ]
        return {
            "ticker": trade["ticker"],
            "qty": float(q),
            "qty_remaining_after": float(max(remaining - q, 0)),
            "order_type": order_type,
            "limit_price": float(limit_price) if limit_price is not None else None,
            "reference_price": float(ref),
            "estimated_value": float(q * ref),
            "estimated_realized_pnl": float((ref - entry) * q),
            "closes_position": q >= remaining,
            "risk_gate": {"allowed": allowed, "reasons": reasons},
        }

    def close(self, trade: dict, qty: Decimal | None, order_type: str,
              limit_price: Decimal | None, price: Decimal, ctx: RiskGateContext,
              actor: str) -> tuple[bool, dict[str, Any], list[str]]:
        """Esegue la chiusura. Restituisce (ok, data, reasons)."""
        if self.halt.is_halted():
            return False, {}, [HALT_REASON]
        preview = self.preview_close(trade, qty, order_type, limit_price, price, ctx)
        if not preview["risk_gate"]["allowed"]:
            return False, preview, preview["risk_gate"]["reasons"]
        closer = getattr(self.broker, "close_position", None)
        if closer is None:
            return False, preview, ["Il broker configurato non supporta la chiusura di posizione"]

        ticker = trade["ticker"]
        q = _dec(preview["qty"])
        full = bool(preview["closes_position"])
        draft = {
            "symbol": ticker, "side": "sell", "entry": str(preview["reference_price"]),
            "stop": None, "take_profit": None, "quantity": str(q), "risk_reward": None,
            "risk_amount": None, "notional": str(q * _dec(preview["reference_price"])),
            "kind": "manual_close", "order_type": order_type, "actor": actor,
        }
        h = hashlib.sha256(json.dumps(draft, sort_keys=True).encode()).hexdigest()
        cid = f"close-{ticker.lower()}-{h[:8]}-{uuid.uuid4().hex[:6]}"
        with self.db.transaction():
            order_id = self.db.insert_order(
                ticker=ticker, side="sell", draft=draft, draft_hash=h,
                approval_status="approved", client_order_id=cid, status="submitting",
            )
            self.db.insert_order_event(order_id, "created",
                                       {"approval_status": "approved", "actor": actor})
            self._emit("order.created", order_id, {
                "order_id": order_id, "ticker": ticker, "side": "sell",
                "status": "submitting", "client_order_id": cid}, actor)

        entry_order = self.db.get_order(int(trade["entry_order_id"])) or {}
        remaining = _remaining(trade)
        try:
            result: CloseResult = closer(
                client_order_id=cid, symbol=ticker, qty=q, order_type=order_type,
                limit_price=limit_price, bracket_order_id=entry_order.get("broker_order_id"),
                residual_qty=remaining - q,
                residual_stop=_dec(trade["stop_price"]) if trade.get("stop_price") else None,
                residual_target=_dec(trade["target_price"]) if trade.get("target_price") else None,
            )
        except Exception as exc:
            logger.exception("Broker close_position failed for %s", ticker)
            with self.db.transaction():
                self.db.insert_order_event(order_id, "broker_error", {"error": str(exc)})
            return False, {**preview, "order_id": order_id}, [f"Errore del broker: {exc}"]

        with self.db.transaction():
            self.db.update_order_status(order_id, status=result.status,
                                        broker_order_id=result.broker_order_id)
            self.db.insert_order_event(order_id, "submitted",
                                       {"broker_order_id": result.broker_order_id})
            self._emit("order.status_changed", order_id, {
                "order_id": order_id, "status": result.status,
                "broker_order_id": result.broker_order_id, "event": "submitted"}, actor)
            if result.residual_order_id:
                self.db.update_order_status(int(trade["entry_order_id"]), status="filled",
                                            broker_order_id=result.residual_order_id)
            if result.status == "filled" and result.fill_price is not None:
                fill_qty = result.filled_qty or q
                self.db.insert_order_event(order_id, "exit_recorded",
                                           {"price": str(result.fill_price), "qty": str(fill_qty)})
                if full and fill_qty >= remaining:
                    self.trade_manager.record_exit_fill(
                        trade_id=int(trade["id"]), exit_price=result.fill_price,
                        exit_reason="pm_sell", ticker=ticker)
                else:
                    self.trade_manager.record_partial_exit(
                        int(trade["id"]), fill_qty, result.fill_price)

        data = {**preview, "order": {
            "order_id": order_id, "client_order_id": cid,
            "broker_order_id": result.broker_order_id, "status": result.status,
            "side": "sell", "order_type": order_type, "qty": float(q)}}
        return True, data, []

    # --- stop / target --------------------------------------------------------------------

    def _open_risk(self, price: Decimal, stop: Decimal | None, qty: Decimal) -> float | None:
        return float(max(price - stop, Decimal(0)) * qty) if stop is not None else None

    def preview_modify(self, trade: dict, stop: Decimal | None, target: Decimal | None,
                       price: Decimal, ctx: RiskGateContext) -> dict[str, Any]:
        remaining = _remaining(trade)
        cur_stop = _dec(trade["stop_price"]) if trade.get("stop_price") else None
        cur_target = _dec(trade["target_price"]) if trade.get("target_price") else None
        reasons: list[str] = []
        if stop is None and target is None:
            reasons.append("Specificare almeno uno tra stop_price e target_price")
        if stop is not None and not 0 < stop < price:
            reasons.append(f"Lo stop {stop} deve essere positivo e sotto il prezzo attuale {price}")
        if target is not None and target <= price:
            reasons.append(f"Il target {target} deve essere sopra il prezzo attuale {price}")
        eff_stop = stop if stop is not None else cur_stop
        eff_target = target if target is not None else cur_target
        if eff_stop is not None and eff_target is not None and eff_stop >= eff_target:
            reasons.append("Lo stop deve restare sotto il target")
        widening = stop is not None and cur_stop is not None and stop < cur_stop
        if widening and not reasons:
            order = GateOrder(symbol=trade["ticker"], side="buy", quantity=remaining,
                              entry=price, stop=stop, take_profit=eff_target or price * 2,
                              sector=ctx.sector_map.get(trade["ticker"], ""))
            res = run_risk_gate(order, ctx, guards=(guard_risk_per_trade,))
            reasons.extend(res.reasons)
        new_risk = self._open_risk(price, eff_stop, remaining)
        return {
            "ticker": trade["ticker"],
            "stop_price": float(eff_stop) if eff_stop is not None else None,
            "target_price": float(eff_target) if eff_target is not None else None,
            "previous_stop_price": float(cur_stop) if cur_stop is not None else None,
            "previous_target_price": float(cur_target) if cur_target is not None else None,
            "widening_stop": widening,
            "tightening_stop": bool(stop is not None and cur_stop is not None and stop > cur_stop),
            "open_risk_before": self._open_risk(price, cur_stop, remaining),
            "open_risk": new_risk,
            "open_risk_fraction": float(_dec(new_risk) / ctx.equity) if new_risk is not None else None,
            "risk_gate": {"allowed": not reasons, "reasons": reasons},
        }

    def modify(self, trade: dict, stop: Decimal | None, target: Decimal | None, price: Decimal,
               ctx: RiskGateContext, actor: str) -> tuple[bool, dict[str, Any], list[str]]:
        preview = self.preview_modify(trade, stop, target, price, ctx)
        if not preview["risk_gate"]["allowed"]:
            return False, preview, preview["risk_gate"]["reasons"]
        try:
            levels = self.trade_manager.set_exit_levels(
                trade["ticker"], stop=stop, target=target, reason="manual", actor=actor)
        except Exception as exc:
            logger.exception("modify_exit failed for %s", trade["ticker"])
            return False, preview, [f"Errore del broker: {exc}"]
        return True, {**preview, **levels}, []

    def _emit(self, type_: str, order_id: int, payload: dict[str, Any], actor: str) -> None:
        if self.event_log is not None:
            self.event_log.append(type=type_, subject=f"order:{order_id}", payload=payload,
                                  actor=actor)
