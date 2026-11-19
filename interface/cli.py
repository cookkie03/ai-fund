"""Command Line Interface for the Trading Agent Office."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from typing import Any, TextIO

from bootstrap import build_office
from config.office_settings import check_config
from data.refresh import refresh_watchlist_and_portfolio
from workflows.office import Office
from workflows.scheduling import TaskSource


def _format_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Format rows as a neat text table."""
    if not rows:
        return "No entries found."

    str_rows = [[str(cell) if cell is not None else "" for cell in row] for row in rows]
    col_widths = [len(h) for h in headers]
    for row in str_rows:
        for idx, cell in enumerate(row):
            if idx < len(col_widths):
                col_widths[idx] = max(col_widths[idx], len(cell))
            else:
                col_widths.append(len(cell))

    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in col_widths))]
    for row in str_rows:
        # Pad row if needed
        padded = row + [""] * (len(col_widths) - len(row))
        lines.append(fmt.format(*padded))
    return "\n".join(lines)


def _cmd_run(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    poll_interval = getattr(args, "poll_interval", 0.5)
    out.write(
        f"Starting Agent Office loop (poll interval: {poll_interval}s)... Press Ctrl+C to stop.\n"
    )
    out.flush()
    try:
        office.run(poll_interval=poll_interval)
    except KeyboardInterrupt:
        out.write("\nStopping Agent Office...\n")
        office.stop()
    return 0


def _cmd_task(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    ticker = args.ticker.upper().strip()
    agent = args.agent.strip()
    reason = args.reason.strip()
    when_ts = args.when.strip() if args.when else office.get_now_iso()

    task_id = office.db.enqueue_scheduled_task(
        agent=agent,
        chat=ticker,
        when_ts=when_ts,
        source=TaskSource.MANUAL.value,
        reason=reason,
        data={"ticker": ticker, "manual": True},
    )
    out.write(f"Enqueued manual task #{task_id} for {agent} on {ticker} (due: {when_ts})\n")
    return 0


def _cmd_say(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    agent = args.agent.strip()
    chat = args.chat.strip()
    text = args.text.strip()
    now_iso = office.get_now_iso()

    chat_id = office.db.get_or_create_chat(agent, chat)
    msg_id = office.db.append_message(
        chat_id=chat_id,
        author="user",
        text=text,
        kind="original",
        ts=now_iso,
    )
    out.write(f"Message #{msg_id} appended to chat '{chat}' ({agent})\n")

    # A message to PM also acts as a manual Scheduled task
    if office._is_pm_agent(agent):
        task_id = office.db.enqueue_scheduled_task(
            agent="portfolio_manager",
            chat=chat.upper(),
            when_ts=now_iso,
            source=TaskSource.MANUAL.value,
            reason=text,
            data={"ticker": chat.upper(), "from_user_say": True},
        )
        out.write(f"Enqueued manual task #{task_id} for PM on {chat.upper()}\n")

    return 0


def _cmd_cycles_list(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    query = "SELECT * FROM cycles WHERE 1=1"
    params: list[Any] = []
    if args.ticker:
        query += " AND ticker = ?"
        params.append(args.ticker.upper().strip())
    query += " ORDER BY id DESC LIMIT ?"
    params.append(args.limit)

    rows = [dict(r) for r in office.db.connection.execute(query, params).fetchall()]
    if args.json:
        out.write(json.dumps(rows, indent=2) + "\n")
        return 0

    headers = ["ID", "TICKER", "STATUS", "OPENED", "CLOSED", "OUTCOME"]
    table_rows = [
        [
            r["id"],
            r["ticker"],
            r["status"],
            r["opened_ts"],
            r.get("closed_ts") or "-",
            r.get("outcome") or "-",
        ]
        for r in rows
    ]
    out.write(_format_table(headers, table_rows) + "\n")
    return 0


def _cmd_cycles_show(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    cycle_id = args.cycle_id
    cycle = office.db.get_cycle(cycle_id)
    if not cycle:
        out.write(f"Error: Cycle #{cycle_id} not found\n")
        return 1

    msg_rows = office.db.connection.execute(
        "SELECT * FROM messages WHERE cycle_id = ? ORDER BY ts ASC, id ASC",
        (cycle_id,),
    ).fetchall()
    messages = [dict(m) for m in msg_rows]

    budget_used = {}
    if cycle.get("budget_used_json"):
        try:
            budget_used = json.loads(cycle["budget_used_json"])
        except Exception:
            budget_used = cycle["budget_used_json"]

    data = {
        "cycle": dict(cycle),
        "budget_used": budget_used,
        "messages": messages,
    }

    if args.json:
        out.write(json.dumps(data, indent=2) + "\n")
        return 0

    out.write(f"=== Cycle #{cycle['id']} ({cycle['ticker']}) ===\n")
    out.write(f"Status:   {cycle['status']}\n")
    out.write(f"Opened:   {cycle['opened_ts']}\n")
    out.write(f"Closed:   {cycle.get('closed_ts') or '-'}\n")
    out.write(f"Outcome:  {cycle.get('outcome') or '-'}\n")
    out.write(f"Budget:   {budget_used}\n")
    out.write(f"Messages ({len(messages)}):\n")
    for m in messages:
        out.write(f"  [{m['ts']}] {m['author']}: {m['text'][:120]}\n")
    return 0


def _cmd_chat_show(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    agent = args.agent.strip()
    topic = args.topic.strip()
    chat_row = office.db.connection.execute(
        "SELECT id FROM chats WHERE agent = ? AND topic = ?", (agent, topic)
    ).fetchone()

    if not chat_row:
        out.write(f"No chat found for agent '{agent}' and topic '{topic}'.\n")
        return 0

    chat_id = int(chat_row["id"])
    messages = office.db.list_messages(
        chat_id=chat_id,
        kind=args.kind,
        limit=args.limit,
    )

    if args.json:
        out.write(json.dumps(messages, indent=2) + "\n")
        return 0

    out.write(f"=== Chat '{topic}' ({agent}) - {len(messages)} messages ===\n")
    for m in messages:
        kind_tag = f" [{m['kind']}]" if m.get("kind") != "original" else ""
        out.write(f"[{m['ts']}]{kind_tag} {m['author']}: {m['text']}\n")
    return 0


def _cmd_state_show(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    ticker = args.ticker.upper().strip()
    state_row = office.db.get_ticker_state(ticker)
    if not state_row or not state_row.get("state_json"):
        out.write(f"No state found for ticker '{ticker}'.\n")
        return 0

    try:
        state_data = json.loads(state_row["state_json"])
    except Exception:
        state_data = state_row["state_json"]

    if args.json:
        out.write(json.dumps(state_data, indent=2) + "\n")
        return 0

    out.write(f"=== Ticker State: {ticker} (updated: {state_row.get('updated_ts')}) ===\n")
    if isinstance(state_data, dict):
        for k, v in state_data.items():
            if isinstance(v, (dict, list)):
                out.write(f"{k}:\n  {json.dumps(v, indent=2)}\n")
            else:
                out.write(f"{k}: {v}\n")
    else:
        out.write(str(state_data) + "\n")
    return 0


def _cmd_watchlist_list(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    items = office.db.list_watchlist()
    if args.json:
        out.write(json.dumps(items, indent=2) + "\n")
        return 0

    headers = ["TICKER", "ADDED_TS", "NOTE"]
    rows = [[it["ticker"], it["added_ts"], it.get("note") or ""] for it in items]
    out.write(_format_table(headers, rows) + "\n")
    return 0


def _cmd_watchlist_add(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    ticker = args.ticker.upper().strip()
    note = getattr(args, "note", "") or ""
    office.db.add_watchlist(ticker, note=note)
    out.write(f"Added {ticker} to watchlist.\n")
    return 0


def _cmd_watchlist_remove(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    ticker = args.ticker.upper().strip()
    ok = office.db.remove_watchlist(ticker)
    if ok:
        out.write(f"Removed {ticker} from watchlist.\n")
    else:
        out.write(f"Ticker {ticker} was not in watchlist.\n")
    return 0


def _cmd_orders_list(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    query = "SELECT * FROM orders WHERE 1=1"
    params: list[Any] = []
    if args.ticker:
        query += " AND ticker = ?"
        params.append(args.ticker.upper().strip())
    if args.status:
        query += " AND (status = ? OR approval_status = ?)"
        params.extend([args.status, args.status])
    query += " ORDER BY id DESC LIMIT ?"
    params.append(args.limit)

    rows = [dict(r) for r in office.db.connection.execute(query, params).fetchall()]
    if args.json:
        out.write(json.dumps(rows, indent=2) + "\n")
        return 0

    headers = ["ID", "TICKER", "SIDE", "STATUS", "APPROVAL", "CLIENT_ID", "BROKER_ID", "CREATED"]
    table_rows = [
        [
            r["id"],
            r["ticker"],
            r["side"],
            r["status"],
            r["approval_status"],
            r["client_order_id"],
            r.get("broker_order_id") or "-",
            r["created_ts"],
        ]
        for r in rows
    ]
    out.write(_format_table(headers, table_rows) + "\n")
    return 0


def _cmd_orders_approve(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    order_id = args.order_id
    outcome = office.order_flow.approve(order_id)
    if outcome.status in ("submitted", "approved"):
        out.write(f"Order #{order_id} approved successfully: status={outcome.status}\n")
        return 0
    else:
        out.write(
            f"Order #{order_id} approval failed / deferred: "
            f"status={outcome.status}, reasons={outcome.reasons}\n"
        )
        return 1


def _cmd_orders_reject(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    order_id = args.order_id
    reason = getattr(args, "reason", "User rejected via CLI")
    outcome = office.order_flow.reject(order_id, reason=reason)
    out.write(f"Order #{order_id} rejected: {outcome.reasons}\n")
    return 0


def _cmd_orders_sync(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    changed = office.order_flow.sync_broker_orders()
    out.write(f"Synced with broker: {len(changed)} order(s) updated {changed}\n")
    return 0


def _cmd_trades_list(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    ticker = args.ticker.upper().strip() if args.ticker else None
    open_only = getattr(args, "open_only", False)

    trade_mgr = getattr(office, "trade_manager", None)
    if trade_mgr is not None:
        trades = trade_mgr.list_trades(ticker=ticker, open_only=open_only)
    else:
        query = "SELECT * FROM trades WHERE 1=1"
        params: list[Any] = []
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)
        if open_only:
            query += " AND closed_ts IS NULL"
        query += " ORDER BY id ASC"
        trades = [dict(r) for r in office.db.connection.execute(query, params).fetchall()]

    if args.json:
        out.write(json.dumps(trades, indent=2) + "\n")
        return 0

    headers = ["ID", "TICKER", "QTY", "ENTRY_PX", "EXIT_PX", "EXIT_REASON", "OPENED", "CLOSED"]
    rows = [
        [
            t["id"],
            t["ticker"],
            t["qty"],
            t["entry_price"],
            t.get("exit_price") or "-",
            t.get("exit_reason") or "-",
            t["opened_ts"],
            t.get("closed_ts") or "-",
        ]
        for t in trades
    ]
    out.write(_format_table(headers, rows) + "\n")
    return 0


def _cmd_portfolio_sync(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    env = office.get_env()
    reader = getattr(office, "broker_reader", None) or env.broker_reader
    acc = reader.get_account()
    positions = reader.get_positions()

    equity = float(acc.get("equity", 0.0) if isinstance(acc, dict) else getattr(acc, "equity", 0.0))
    cash = float(acc.get("cash", 0.0) if isinstance(acc, dict) else getattr(acc, "cash", 0.0))

    now_ts = office.get_now_iso()
    office.db.insert_portfolio_snapshot(
        equity=equity,
        cash=cash,
        positions=positions,
        ts=now_ts,
    )

    if getattr(args, "json", False):
        out.write(
            json.dumps(
                {"ts": now_ts, "equity": equity, "cash": cash, "positions": positions},
                indent=2,
            )
            + "\n"
        )
        return 0

    out.write(f"Portfolio synchronized at {now_ts}:\n")
    out.write(f"  Equity:    ${equity:,.2f}\n")
    out.write(f"  Cash:      ${cash:,.2f}\n")
    out.write(f"  Positions: {len(positions)}\n")
    for p in positions:
        sym = p.get("symbol") if isinstance(p, dict) else getattr(p, "symbol", "")
        qty = p.get("qty") if isinstance(p, dict) else getattr(p, "qty", 0)
        mv = p.get("market_value") if isinstance(p, dict) else getattr(p, "market_value", 0.0)
        out.write(f"    - {sym}: {qty} shares (${mv:,.2f})\n")
    return 0


def _cmd_data_refresh(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    cache = getattr(office, "data_cache", None)
    if cache is None:
        out.write("DataCache is not attached to this office instance.\n")
        return 0

    tickers = [t.upper().strip() for t in args.tickers] if args.tickers else None
    force = getattr(args, "force", False)
    kinds = [k.strip() for k in args.kinds.split(",")] if getattr(args, "kinds", None) else None

    result = refresh_watchlist_and_portfolio(
        cache=cache,
        tickers=tickers,
        force=force,
        kinds=kinds,
    )
    out.write(f"Data refresh completed: {len(result)} items processed.\n")
    return 0


def _cmd_inbox(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    if getattr(args, "mark_read", None) is not None:
        office.db.mark_inbox_read(args.mark_read)
        out.write(f"Marked inbox item #{args.mark_read} as read.\n")
        return 0

    unread_only = getattr(args, "unread_only", False)
    limit = getattr(args, "limit", 50)
    items = office.db.list_inbox(unread_only=unread_only, limit=limit)

    if getattr(args, "json", False):
        out.write(json.dumps(items, indent=2) + "\n")
        return 0

    headers = ["ID", "TS", "READ", "KIND", "TEXT"]
    rows = [
        [
            it["id"],
            it["ts"],
            "Yes" if it.get("read") else "No",
            it["kind"],
            it["text"][:80],
        ]
        for it in items
    ]
    out.write(_format_table(headers, rows) + "\n")
    return 0


def _cmd_halt(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    cancel_open = getattr(args, "cancel_open", True)
    office.halt.halt(cancel_open=cancel_open)
    out.write(f"System halted. Trading stopped (cancel_open={cancel_open}).\n")
    return 0


def _cmd_resume(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    office.halt.resume()
    out.write("System resumed. Trading allowed.\n")
    return 0


def _cmd_config_check(office: Office, args: argparse.Namespace, out: TextIO) -> int:
    problems = check_config(office.settings)
    if getattr(args, "json", False):
        out.write(json.dumps({"problems": problems, "ok": len(problems) == 0}, indent=2) + "\n")
        return 1 if problems else 0

    if problems:
        out.write("Configuration issues found:\n")
        for p in problems:
            out.write(f"  - {p}\n")
        return 1
    else:
        out.write("Configuration check passed: no issues found.\n")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading-agent",
        description="Autonomous Agent Office CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. run
    p_run = subparsers.add_parser("run", help="Run the Agent Office scheduler loop")
    p_run.add_argument("--poll-interval", type=float, default=0.5, help="Poll interval in seconds")
    p_run.set_defaults(handler=_cmd_run)

    # 2. task
    p_task = subparsers.add_parser("task", help="Create a manual Scheduled task on a ticker")
    p_task.add_argument("ticker", help="Ticker symbol (e.g. AAPL)")
    p_task.add_argument("--agent", default="portfolio_manager", help="Target agent")
    p_task.add_argument("--reason", default="Manual task via CLI", help="Task reason/note")
    p_task.add_argument("--when", default=None, help="Due ISO timestamp (defaults to now)")
    p_task.set_defaults(handler=_cmd_task)

    # 3. say
    p_say = subparsers.add_parser("say", help="Send a message to an agent's chat")
    p_say.add_argument("agent", help="Agent name (e.g. portfolio_manager, market_analyst)")
    p_say.add_argument("chat", help="Chat topic or ticker (e.g. AAPL, macro)")
    p_say.add_argument("text", help="Message text")
    p_say.set_defaults(handler=_cmd_say)

    # 4. cycles
    p_cycles = subparsers.add_parser("cycles", help="Inspect analysis cycles")
    sp_cycles = p_cycles.add_subparsers(dest="subcommand", required=True)

    sp_c_list = sp_cycles.add_parser("list", help="List analysis cycles")
    sp_c_list.add_argument("--ticker", default=None, help="Filter by ticker")
    sp_c_list.add_argument("--limit", type=int, default=20, help="Max entries")
    sp_c_list.add_argument("--json", action="store_true", help="Output JSON")
    sp_c_list.set_defaults(handler=_cmd_cycles_list)

    sp_c_show = sp_cycles.add_parser("show", help="Show cycle details and messages")
    sp_c_show.add_argument("cycle_id", type=int, help="Cycle ID")
    sp_c_show.add_argument("--json", action="store_true", help="Output JSON")
    sp_c_show.set_defaults(handler=_cmd_cycles_show)

    # 5. chat
    p_chat = subparsers.add_parser("chat", help="Inspect agent chats")
    sp_chat = p_chat.add_subparsers(dest="subcommand", required=True)

    sp_ch_show = sp_chat.add_parser("show", help="Show messages in a chat")
    sp_ch_show.add_argument("agent", help="Agent name")
    sp_ch_show.add_argument("topic", help="Topic or ticker")
    sp_ch_show.add_argument("--limit", type=int, default=50, help="Max messages")
    sp_ch_show.add_argument(
        "--kind", default=None, help="Filter by message kind (original/summary)"
    )
    sp_ch_show.add_argument("--json", action="store_true", help="Output JSON")
    sp_ch_show.set_defaults(handler=_cmd_chat_show)

    # 6. state
    p_state = subparsers.add_parser("state", help="Inspect ticker state")
    sp_state = p_state.add_subparsers(dest="subcommand", required=True)

    sp_st_show = sp_state.add_parser("show", help="Show state for a ticker")
    sp_st_show.add_argument("ticker", help="Ticker symbol")
    sp_st_show.add_argument("--json", action="store_true", help="Output JSON")
    sp_st_show.set_defaults(handler=_cmd_state_show)

    # 7. watchlist
    p_watch = subparsers.add_parser("watchlist", help="Manage watchlist")
    sp_watch = p_watch.add_subparsers(dest="subcommand", required=True)

    sp_w_list = sp_watch.add_parser("list", help="List watchlist")
    sp_w_list.add_argument("--json", action="store_true", help="Output JSON")
    sp_w_list.set_defaults(handler=_cmd_watchlist_list)

    sp_w_add = sp_watch.add_parser("add", help="Add ticker to watchlist")
    sp_w_add.add_argument("ticker", help="Ticker symbol")
    sp_w_add.add_argument("--note", default="", help="Optional note")
    sp_w_add.set_defaults(handler=_cmd_watchlist_add)

    sp_w_rem = sp_watch.add_parser("remove", help="Remove ticker from watchlist")
    sp_w_rem.add_argument("ticker", help="Ticker symbol")
    sp_w_rem.set_defaults(handler=_cmd_watchlist_remove)

    # 8. orders
    p_orders = subparsers.add_parser("orders", help="Inspect and govern orders")
    sp_orders = p_orders.add_subparsers(dest="subcommand", required=True)

    sp_o_list = sp_orders.add_parser("list", help="List orders")
    sp_o_list.add_argument("--ticker", default=None, help="Filter by ticker")
    sp_o_list.add_argument("--status", default=None, help="Filter by status")
    sp_o_list.add_argument("--limit", type=int, default=50, help="Max orders")
    sp_o_list.add_argument("--json", action="store_true", help="Output JSON")
    sp_o_list.set_defaults(handler=_cmd_orders_list)

    sp_o_app = sp_orders.add_parser("approve", help="Approve an order in approval queue")
    sp_o_app.add_argument("order_id", type=int, help="Order ID to approve")
    sp_o_app.set_defaults(handler=_cmd_orders_approve)

    sp_o_rej = sp_orders.add_parser("reject", help="Reject an order in approval queue")
    sp_o_rej.add_argument("order_id", type=int, help="Order ID to reject")
    sp_o_rej.add_argument("--reason", default="User rejected via CLI", help="Rejection reason")
    sp_o_rej.set_defaults(handler=_cmd_orders_reject)

    sp_o_sync = sp_orders.add_parser("sync", help="Align submitted orders with broker state")
    sp_o_sync.set_defaults(handler=_cmd_orders_sync)

    # 9. trades
    p_trades = subparsers.add_parser("trades", help="Inspect trades")
    sp_trades = p_trades.add_subparsers(dest="subcommand", required=True)

    sp_t_list = sp_trades.add_parser("list", help="List trades")
    sp_t_list.add_argument("--ticker", default=None, help="Filter by ticker")
    sp_t_list.add_argument("--open-only", action="store_true", help="List only open trades")
    sp_t_list.add_argument("--json", action="store_true", help="Output JSON")
    sp_t_list.set_defaults(handler=_cmd_trades_list)

    # 10. portfolio
    p_port = subparsers.add_parser("portfolio", help="Portfolio management")
    sp_port = p_port.add_subparsers(dest="subcommand", required=True)

    sp_p_sync = sp_port.add_parser("sync", help="Synchronize portfolio from broker")
    sp_p_sync.add_argument("--json", action="store_true", help="Output JSON")
    sp_p_sync.set_defaults(handler=_cmd_portfolio_sync)

    # 11. data
    p_data = subparsers.add_parser("data", help="Financial data cache operations")
    sp_data = p_data.add_subparsers(dest="subcommand", required=True)

    sp_d_ref = sp_data.add_parser("refresh", help="Force refresh of data cache")
    sp_d_ref.add_argument("tickers", nargs="*", default=None, help="Tickers to refresh")
    sp_d_ref.add_argument("--force", action="store_true", help="Force refresh even if not expired")
    sp_d_ref.add_argument("--kinds", default=None, help="Comma-separated kinds")
    sp_d_ref.set_defaults(handler=_cmd_data_refresh)

    # 12. inbox
    p_inbox = subparsers.add_parser("inbox", help="View alerts and notifications")
    p_inbox.add_argument("--unread-only", action="store_true", help="Show unread only")
    p_inbox.add_argument("--limit", type=int, default=50, help="Max entries")
    p_inbox.add_argument("--mark-read", type=int, default=None, help="Mark item ID as read")
    p_inbox.add_argument("--json", action="store_true", help="Output JSON")
    p_inbox.set_defaults(handler=_cmd_inbox)

    # 13. halt
    p_halt = subparsers.add_parser("halt", help="Halt the trading engine")
    p_halt.add_argument(
        "--cancel-open",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Cancel open orders on halt (default: True)",
    )
    p_halt.set_defaults(handler=_cmd_halt)

    # 14. resume
    p_resume = subparsers.add_parser("resume", help="Resume trading operations")
    p_resume.set_defaults(handler=_cmd_resume)

    # 15. config
    p_cfg = subparsers.add_parser("config", help="Configuration inspection")
    sp_cfg = p_cfg.add_subparsers(dest="subcommand", required=True)

    sp_c_chk = sp_cfg.add_parser("check", help="Verify configuration and credentials")
    sp_c_chk.add_argument("--json", action="store_true", help="Output JSON")
    sp_c_chk.set_defaults(handler=_cmd_config_check)

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    office_factory: Callable[[], Office] | None = None,
    out: TextIO = sys.stdout,
) -> int:
    """CLI entrypoint. Returns exit code (0 on success, non-zero on failure)."""
    raw_args = list(argv if argv is not None else sys.argv[1:])
    parser = build_parser()

    subcmds = (
        "run", "task", "say", "cycles", "chat", "state", "watchlist",
        "orders", "trades", "portfolio", "data", "inbox", "halt", "resume", "config",
    )
    if any(a in ("-h", "--help") for a in raw_args) and not any(a in subcmds for a in raw_args):
        parser.print_help(out)
        return 0

    try:
        args = parser.parse_args(raw_args)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    if getattr(args, "command", "") == "config" and office_factory is None:
        # config check must report problems, not require a working broker/DB
        from dotenv import dotenv_values

        from config.office_settings import load_office_settings

        env = {**dotenv_values(".env"), **os.environ}
        problems = check_config(load_office_settings(), env)
        if getattr(args, "json", False):
            out.write(json.dumps({"problems": problems, "ok": not problems}, indent=2) + "\n")
        elif problems:
            out.write("Configuration issues found:\n")
            out.writelines(f"  - {p}\n" for p in problems)
        else:
            out.write("Configuration check passed: no issues found.\n")
        return 1 if problems else 0

    # Instantiate office
    try:
        office = office_factory() if office_factory is not None else build_office()
    except Exception as exc:
        out.write(f"Failed to initialize Agent Office: {exc}\n")
        return 1

    # Log command execution in cli_commands table
    cmd_name = getattr(args, "command", "")
    sub_name = getattr(args, "subcommand", None)
    full_cmd = f"{cmd_name} {sub_name}".strip() if sub_name else cmd_name
    cmd_args = {
        k: v for k, v in vars(args).items() if k not in ("handler", "command", "subcommand")
    }

    try:
        office.db.log_cli_command(full_cmd, cmd_args)
    except Exception:
        pass

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(out)
        return 1

    try:
        return handler(office, args, out)
    except Exception as exc:
        out.write(f"Command execution error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
