"""Command handlers executing domain logic within the single-writer runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from runtime.commands import (
    AddWatchlist,
    ApproveOrder,
    CommandResult,
    EnqueueTask,
    Halt,
    IngestAlert,
    MarkInboxRead,
    ReconcileBroker,
    RefreshData,
    RejectOrder,
    RemoveWatchlist,
    Resume,
    Say,
)
from workflows.scheduling import TaskSource

if TYPE_CHECKING:
    from runtime.core import RuntimeContext


def handle_enqueue_task(ctx: RuntimeContext, cmd: EnqueueTask, actor: str) -> CommandResult:
    ticker = cmd.ticker.upper().strip()
    agent = cmd.agent.strip()
    reason = cmd.reason.strip()
    when_ts = cmd.when_ts.strip() if cmd.when_ts else ctx.office.get_now_iso()

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
        payload={"task_id": task_id, "agent": agent, "ticker": ticker, "reason": reason, "when_ts": when_ts},
        actor=actor,
    )

    return CommandResult(ok=True, data={"task_id": task_id, "due": when_ts})


def handle_say(ctx: RuntimeContext, cmd: Say, actor: str) -> CommandResult:
    agent = cmd.agent.strip()
    chat = cmd.chat.strip()
    text = cmd.text.strip()
    now_iso = ctx.office.get_now_iso()

    chat_id = ctx.office.db.get_or_create_chat(agent, chat)
    msg_id = ctx.office.db.append_message(
        chat_id=chat_id,
        author=actor,
        text=text,
        kind="original",
        ts=now_iso,
    )

    ctx.event_log.append(
        type="message.appended",
        subject=f"chat:{chat_id}",
        payload={"chat_id": chat_id, "message_id": msg_id, "agent": agent, "topic": chat, "text": text},
        actor=actor,
    )

    data: dict[str, Any] = {"message_id": msg_id, "chat_id": chat_id}

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
            payload={"task_id": task_id, "agent": "portfolio_manager", "ticker": chat.upper(), "reason": text},
            actor=actor,
        )
        data["task_id"] = task_id

    return CommandResult(ok=True, data=data)


def handle_add_watchlist(ctx: RuntimeContext, cmd: AddWatchlist, actor: str) -> CommandResult:
    ticker = cmd.ticker.upper().strip()
    note = cmd.note or ""
    ctx.office.db.add_watchlist(ticker, note=note)

    ctx.event_log.append(
        type="watchlist.changed",
        subject=f"ticker:{ticker}",
        payload={"action": "add", "ticker": ticker, "note": note},
        actor=actor,
    )

    return CommandResult(ok=True, data={"ticker": ticker})


def handle_remove_watchlist(ctx: RuntimeContext, cmd: RemoveWatchlist, actor: str) -> CommandResult:
    ticker = cmd.ticker.upper().strip()
    ok = ctx.office.db.remove_watchlist(ticker)

    if ok:
        ctx.event_log.append(
            type="watchlist.changed",
            subject=f"ticker:{ticker}",
            payload={"action": "remove", "ticker": ticker},
            actor=actor,
        )

    return CommandResult(ok=ok, data={"ticker": ticker})


def handle_approve_order(ctx: RuntimeContext, cmd: ApproveOrder, actor: str) -> CommandResult:
    outcome = ctx.office.order_flow.approve(cmd.order_id)
    if outcome.status in ("submitted", "approved"):
        ctx.event_log.append(
            type="order.approved",
            subject=f"order:{cmd.order_id}",
            payload={"order_id": cmd.order_id, "status": outcome.status},
            actor=actor,
        )
        return CommandResult(ok=True, data={"order_id": cmd.order_id, "status": outcome.status, "reasons": outcome.reasons})
    else:
        return CommandResult(ok=False, data={"order_id": cmd.order_id, "status": outcome.status}, reasons=outcome.reasons)


def handle_reject_order(ctx: RuntimeContext, cmd: RejectOrder, actor: str) -> CommandResult:
    outcome = ctx.office.order_flow.reject(cmd.order_id, reason=cmd.reason)
    ctx.event_log.append(
        type="order.rejected",
        subject=f"order:{cmd.order_id}",
        payload={"order_id": cmd.order_id, "reason": cmd.reason},
        actor=actor,
    )
    return CommandResult(ok=True, data={"order_id": cmd.order_id, "status": outcome.status, "reasons": outcome.reasons})


def handle_halt(ctx: RuntimeContext, cmd: Halt, actor: str) -> CommandResult:
    ctx.office.halt.halt(cancel_open=cmd.cancel_open)
    ctx.event_log.append(
        type="halt.changed",
        subject="halt",
        payload={"halted": True, "cancel_open": cmd.cancel_open},
        actor=actor,
    )
    return CommandResult(ok=True, data={"halted": True, "cancel_open": cmd.cancel_open})


def handle_resume(ctx: RuntimeContext, cmd: Resume, actor: str) -> CommandResult:
    ctx.office.halt.resume()
    ctx.event_log.append(
        type="halt.changed",
        subject="halt",
        payload={"halted": False},
        actor=actor,
    )
    return CommandResult(ok=True, data={"halted": False})


def handle_reconcile_broker(ctx: RuntimeContext, cmd: ReconcileBroker, actor: str) -> CommandResult:
    changed = ctx.office.order_flow.sync_broker_orders()

    env = ctx.office.get_env()
    reader = getattr(ctx.office, "broker_reader", None) or env.broker_reader
    acc = reader.get_account()
    positions = reader.get_positions()

    equity = float(acc.get("equity", 0.0) if isinstance(acc, dict) else getattr(acc, "equity", 0.0))
    cash = float(acc.get("cash", 0.0) if isinstance(acc, dict) else getattr(acc, "cash", 0.0))

    now_ts = ctx.office.get_now_iso()
    ctx.office.db.insert_portfolio_snapshot(
        equity=equity,
        cash=cash,
        positions=positions,
        ts=now_ts,
    )

    ctx.event_log.append(
        type="portfolio.synced",
        subject="portfolio",
        payload={"ts": now_ts, "equity": equity, "cash": cash, "positions_count": len(positions)},
        actor=actor,
    )

    return CommandResult(ok=True, data={"orders_synced": len(changed), "portfolio_synced": True})


def handle_refresh_data(ctx: RuntimeContext, cmd: RefreshData, actor: str) -> CommandResult:
    result = ctx.office.refresh_data(force=cmd.force, kinds=cmd.kinds) or {}
    ctx.event_log.append(
        type="data.refreshed",
        subject="data",
        payload={"kinds": cmd.kinds, "force": cmd.force, "count": len(result)},
        actor=actor,
    )
    return CommandResult(ok=True, data={"count": len(result)})


def handle_mark_inbox_read(ctx: RuntimeContext, cmd: MarkInboxRead, actor: str) -> CommandResult:
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
    ctx.event_log.append(
        type="task.enqueued",
        subject=f"task:{task_id}",
        payload={"task_id": task_id, "ticker": cmd.ticker, "source": cmd.source, "reason": cmd.reason},
        actor=actor,
    )
    return CommandResult(ok=True, data={"task_id": task_id})
