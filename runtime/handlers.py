"""Command handlers for the single-writer runtime."""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING, Any

from runtime.commands import (
    AddWatchlist,
    ApproveOrder,
    ClosePosition,
    CommandResult,
    EnqueueTask,
    Halt,
    IngestAlert,
    MarkInboxRead,
    ModifyExit,
    ReconcileBroker,
    RefreshData,
    RejectOrder,
    RemoveWatchlist,
    Resume,
    Say,
    StrikeAnnotation,
    UpdateRiskLimits,
    UpsertAnnotation,
)
from workflows.scheduling import TaskSource

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from runtime.core import RuntimeContext


def handle_enqueue_task(ctx: RuntimeContext, cmd: EnqueueTask, actor: str) -> CommandResult:
    ticker = cmd.ticker.upper().strip()
    agent = cmd.agent.strip()
    reason = cmd.reason.strip()
    when_ts = cmd.when_ts.strip() if cmd.when_ts else ctx.office.get_now_iso()

    with ctx.office.db.transaction():
        task_id = ctx.office.db.enqueue_scheduled_task(
            agent=agent,
            chat=ticker,
            when_ts=when_ts,
            source=TaskSource.MANUAL.value,
            reason=reason,
            data={"ticker": ticker, "manual": True},
        )

        ctx.event_log.append(
            type="task.enqueued",
            subject=f"task:{task_id}",
            payload={
                "task_id": task_id,
                "agent": agent,
                "ticker": ticker,
                "reason": reason,
                "when_ts": when_ts,
            },
            actor=actor,
        )

    return CommandResult(ok=True, data={"task_id": task_id, "due": when_ts})


def handle_say(ctx: RuntimeContext, cmd: Say, actor: str) -> CommandResult:
    agent = cmd.agent.strip()
    chat = cmd.chat.strip()
    text = cmd.text.strip()
    now_iso = ctx.office.get_now_iso()

    data: dict[str, Any] = {}
    with ctx.office.db.transaction():
        chat_id = ctx.office.db.get_or_create_chat(agent, chat)
        msg_id = ctx.office.db.append_message(
            chat_id=chat_id,
            author="user",
            text=text,
            kind="original",
            ts=now_iso,
        )

        ctx.event_log.append(
            type="message.appended",
            subject=f"chat:{chat_id}",
            payload={
                "chat_id": chat_id,
                "message_id": msg_id,
                "agent": agent,
                "topic": chat,
                "text": text,
            },
            actor=actor,
        )
        data = {"message_id": msg_id, "chat_id": chat_id}

        # Business rule: a message to PM enqueues a Scheduled task
        if ctx.office._is_pm_agent(agent):
            task_id = ctx.office.db.enqueue_scheduled_task(
                agent="portfolio_manager",
                chat=chat.upper(),
                when_ts=now_iso,
                source=TaskSource.MANUAL.value,
                reason=text,
                data={"ticker": chat.upper(), "from_user_say": True},
            )
            ctx.event_log.append(
                type="task.enqueued",
                subject=f"task:{task_id}",
                payload={
                    "task_id": task_id,
                    "agent": "portfolio_manager",
                    "ticker": chat.upper(),
                    "reason": text,
                },
                actor=actor,
            )
            data["task_id"] = task_id

    return CommandResult(ok=True, data=data)


def handle_add_watchlist(ctx: RuntimeContext, cmd: AddWatchlist, actor: str) -> CommandResult:
    ticker = cmd.ticker.upper().strip()
    note = cmd.note or ""
    with ctx.office.db.transaction():
        ctx.office.db.add_watchlist(ticker, note=note, added_by=actor)

        ctx.event_log.append(
            type="watchlist.changed",
            subject=f"ticker:{ticker}",
            payload={"action": "add", "ticker": ticker, "note": note},
            actor=actor,
        )

    return CommandResult(ok=True, data={"ticker": ticker})


def handle_remove_watchlist(ctx: RuntimeContext, cmd: RemoveWatchlist, actor: str) -> CommandResult:
    ticker = cmd.ticker.upper().strip()
    with ctx.office.db.transaction():
        ok = ctx.office.db.remove_watchlist(ticker)

        if ok:
            ctx.event_log.append(
                type="watchlist.changed",
                subject=f"ticker:{ticker}",
                payload={"action": "remove", "ticker": ticker},
                actor=actor,
            )

    return CommandResult(ok=ok, data={"ticker": ticker})


def handle_upsert_annotation(
    ctx: RuntimeContext, cmd: UpsertAnnotation, actor: str
) -> CommandResult:
    conn = ctx.office.db.connection
    existing = conn.execute("SELECT * FROM chart_annotations WHERE id = ?", (cmd.id,)).fetchone()
    if existing and existing["status"] == "struck":
        return CommandResult(ok=False, reasons=["Annotation is struck"])
    ticker = cmd.ticker.strip().upper()
    if existing and existing["ticker"] == ticker and existing["timeframe"] == cmd.timeframe and json.loads(existing["drawing_json"]) == cmd.drawing:
        return CommandResult(ok=True, data={"id": cmd.id})
    now = ctx.office.get_now_iso()
    conn.execute(
        """INSERT INTO chart_annotations (id, ticker, timeframe, drawing_json, author, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET
        ticker=excluded.ticker, timeframe=excluded.timeframe, drawing_json=excluded.drawing_json,
        updated_at=excluded.updated_at""",
        (cmd.id, ticker, cmd.timeframe, json.dumps(cmd.drawing), actor, now, now),
    )
    ctx.event_log.append(
        type="annotation.updated" if existing else "annotation.created",
        subject=f"annotation:{cmd.id}",
        payload={"id": cmd.id, "ticker": ticker},
        actor=actor,
    )
    return CommandResult(ok=True, data={"id": cmd.id})


def handle_strike_annotation(
    ctx: RuntimeContext, cmd: StrikeAnnotation, actor: str
) -> CommandResult:
    conn = ctx.office.db.connection
    existing = conn.execute(
        "SELECT ticker, status FROM chart_annotations WHERE id = ?", (cmd.id,)
    ).fetchone()
    if not existing:
        return CommandResult(ok=False, reasons=["Annotation not found"])
    if existing["status"] == "active":
        now = ctx.office.get_now_iso()
        conn.execute(
            "UPDATE chart_annotations SET status='struck', struck_by=?, struck_at=?, updated_at=? WHERE id=?",
            (actor, now, now, cmd.id),
        )
        ctx.event_log.append(
            type="annotation.struck",
            subject=f"annotation:{cmd.id}",
            payload={"id": cmd.id, "ticker": existing["ticker"]},
            actor=actor,
        )
    return CommandResult(ok=True, data={"id": cmd.id})


def handle_approve_order(ctx: RuntimeContext, cmd: ApproveOrder, actor: str) -> CommandResult:
    fresh_ctx = ctx.office.build_risk_gate_context()
    outcome = ctx.office.order_flow.approve(cmd.order_id, ctx=fresh_ctx)
    if outcome.status in ("submitted", "approved"):
        return CommandResult(
            ok=True,
            data={"order_id": cmd.order_id, "status": outcome.status, "reasons": outcome.reasons},
        )
    else:
        return CommandResult(
            ok=False,
            data={"order_id": cmd.order_id, "status": outcome.status},
            reasons=outcome.reasons,
        )


def handle_reject_order(ctx: RuntimeContext, cmd: RejectOrder, actor: str) -> CommandResult:
    outcome = ctx.office.order_flow.reject(cmd.order_id, reason=cmd.reason)
    return CommandResult(
        ok=True,
        data={"order_id": cmd.order_id, "status": outcome.status, "reasons": outcome.reasons},
    )


def handle_halt(ctx: RuntimeContext, cmd: Halt, actor: str) -> CommandResult:
    ctx.office.halt.halt(cancel_open=cmd.cancel_open)
    return CommandResult(ok=True, data={"halted": True, "cancel_open": cmd.cancel_open})


def handle_resume(ctx: RuntimeContext, cmd: Resume, actor: str) -> CommandResult:
    ctx.office.halt.resume()
    return CommandResult(ok=True, data={"halted": False})


def handle_reconcile_broker(ctx: RuntimeContext, cmd: ReconcileBroker, actor: str) -> CommandResult:
    changed = ctx.office.order_flow.sync_broker_orders()

    env = ctx.office.get_env()
    reader = getattr(ctx.office, "broker_reader", None) or getattr(env, "broker_reader", None)
    acc = reader.get_account() if reader else {}
    positions = reader.get_positions() if reader else ()

    equity = float(acc.get("equity", 0.0) if isinstance(acc, dict) else getattr(acc, "equity", 0.0))
    cash = float(acc.get("cash", 0.0) if isinstance(acc, dict) else getattr(acc, "cash", 0.0))

    now_ts = ctx.office.get_now_iso()
    with ctx.office.db.transaction():
        ctx.office.db.insert_portfolio_snapshot(
            equity=equity,
            cash=cash,
            positions=positions,
            ts=now_ts,
        )

        ctx.event_log.append(
            type="portfolio.synced",
            subject="portfolio",
            payload={
                "ts": now_ts,
                "equity": equity,
                "cash": cash,
                "positions_count": len(positions),
            },
            actor=actor,
        )
        ctx.event_log.append(
            type="portfolio.updated",
            subject="portfolio",
            payload={"reason": "reconcile", "ts": now_ts, "equity": equity, "cash": cash},
            actor=actor,
        )

    return CommandResult(ok=True, data={"orders_synced": len(changed), "portfolio_synced": True})


def handle_refresh_data(ctx: RuntimeContext, cmd: RefreshData, actor: str) -> CommandResult:
    def _run_refresh():
        try:
            result = ctx.office.refresh_data(force=cmd.force, kinds=cmd.kinds) or {}
            with ctx.office.db.transaction():
                ctx.event_log.append(
                    type="data.refreshed",
                    subject="data",
                    payload={"kinds": cmd.kinds, "force": cmd.force, "count": len(result)},
                    actor=actor,
                )
        except Exception as exc:
            logger.exception("Async refresh_data failed: %s", exc)

    thread = threading.Thread(target=_run_refresh, daemon=True, name="refresh-data-worker")
    thread.start()
    return CommandResult(ok=True, data={"status": "accepted", "kinds": cmd.kinds})


def handle_mark_inbox_read(ctx: RuntimeContext, cmd: MarkInboxRead, actor: str) -> CommandResult:
    with ctx.office.db.transaction():
        ctx.office.db.mark_inbox_read(cmd.item_id)
        ctx.event_log.append(
            type="inbox.changed",
            subject=f"inbox:{cmd.item_id}",
            payload={"item_id": cmd.item_id, "read": True},
            actor=actor,
        )
    return CommandResult(ok=True, data={"item_id": cmd.item_id})


def handle_ingest_alert(ctx: RuntimeContext, cmd: IngestAlert, actor: str) -> CommandResult:
    task_id = ctx.office.ingest_external_alert(
        alert_type=cmd.source,
        ticker=cmd.ticker,
        reason=cmd.reason,
        data=cmd.data,
    )
    with ctx.office.db.transaction():
        ctx.event_log.append(
            type="task.enqueued",
            subject=f"task:{task_id}",
            payload={
                "task_id": task_id,
                "ticker": cmd.ticker,
                "source": cmd.source,
                "reason": cmd.reason,
            },
            actor=actor,
        )
    return CommandResult(ok=True, data={"task_id": task_id})


def handle_update_risk_limits(
    ctx: RuntimeContext, cmd: UpdateRiskLimits, actor: str
) -> CommandResult:
    from execution.risk_limits import (
        LimitsValidationError,
        RiskLimitsStore,
        defaults_from_settings,
    )

    store = RiskLimitsStore(ctx.office.db, defaults_from_settings(ctx.office.settings.limits))
    try:
        active = store.update(cmd.limits, cmd.reason, actor)
    except LimitsValidationError as exc:
        return CommandResult(ok=False, reasons=exc.reasons)
    return CommandResult(
        ok=True,
        data={"version": active.version, "limits": active.limits,
              "updated_ts": active.updated_ts, "updated_by": active.updated_by},
    )


def _position_exits(ctx: RuntimeContext) -> Any:
    from execution.position_exits import PositionExits

    office = ctx.office
    return PositionExits(
        office.db,
        office.order_flow.broker,
        office.halt,
        office.order_flow.trade_manager,
        event_log=ctx.event_log,
    )


def _open_trade_and_price(ctx: RuntimeContext, ticker: str) -> tuple[dict | None, Any]:
    from decimal import Decimal

    from runtime import portfolio

    sym = ticker.upper().strip()
    conn = ctx.office.db.connection
    row = conn.execute(
        "SELECT * FROM trades WHERE ticker = ? AND closed_ts IS NULL ORDER BY id DESC LIMIT 1",
        (sym,),
    ).fetchone()
    if row is None:
        return None, None
    trade = dict(row)
    price = portfolio.current_price(conn, sym)
    if price is None:
        price = trade["entry_price"]
    return trade, Decimal(str(price))


def _dec_or_none(value: Any) -> Any:
    from decimal import Decimal

    return Decimal(str(value)) if value is not None else None


def handle_close_position(ctx: RuntimeContext, cmd: ClosePosition, actor: str) -> CommandResult:
    trade, price = _open_trade_and_price(ctx, cmd.ticker)
    if trade is None:
        return CommandResult(ok=False, reasons=[f"Nessuna posizione aperta su {cmd.ticker.upper()}"])
    exits = _position_exits(ctx)
    gate_ctx = ctx.office.build_risk_gate_context()
    qty, limit = _dec_or_none(cmd.qty), _dec_or_none(cmd.limit_price)
    if cmd.dry_run:
        preview = exits.preview_close(trade, qty, cmd.order_type, limit, price, gate_ctx)
        if ctx.office.halt.is_halted():
            preview["risk_gate"] = {"allowed": False, "reasons": [
                "System is halted: all order submissions blocked"]}
        return CommandResult(ok=True, data={"dry_run": True, **preview})
    ok, data, reasons = exits.close(trade, qty, cmd.order_type, limit, price, gate_ctx, actor)
    return CommandResult(ok=ok, data=data, reasons=reasons)


def handle_modify_exit(ctx: RuntimeContext, cmd: ModifyExit, actor: str) -> CommandResult:
    trade, price = _open_trade_and_price(ctx, cmd.ticker)
    if trade is None:
        return CommandResult(ok=False, reasons=[f"Nessuna posizione aperta su {cmd.ticker.upper()}"])
    exits = _position_exits(ctx)
    gate_ctx = ctx.office.build_risk_gate_context()
    stop, target = _dec_or_none(cmd.stop_price), _dec_or_none(cmd.target_price)
    if cmd.dry_run:
        preview = exits.preview_modify(trade, stop, target, price, gate_ctx)
        return CommandResult(ok=True, data={"dry_run": True, **preview})
    ok, data, reasons = exits.modify(trade, stop, target, price, gate_ctx, actor)
    return CommandResult(ok=ok, data=data, reasons=reasons)
