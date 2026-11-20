"""Command Line Interface for the Trading Agent Office (Thin Client)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from typing import Any, TextIO

from config.office_settings import check_config
from interface.client import RuntimeClient, RuntimeUnavailable


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
        padded = row + [""] * (len(col_widths) - len(row))
        lines.append(fmt.format(*padded))
    return "\n".join(lines)


def _cmd_run(runtime_factory: Callable[[], Any] | None, args: argparse.Namespace, out: TextIO) -> int:
    import threading

    import uvicorn

    from runtime.core import Runtime
    from runtime.http import create_app

    host = getattr(args, "host", None) or os.environ.get("TRADING_AGENT_API_HOST", "127.0.0.1")
    port = int(getattr(args, "port", None) or os.environ.get("TRADING_AGENT_API_PORT", "8765"))
    token = getattr(args, "token", None) or os.environ.get("TRADING_AGENT_API_TOKEN")

    poll_interval = getattr(args, "poll_interval", 0.5)
    out.write(
        f"Starting Agent Office loop / Trading Agent Runtime on {host}:{port} (poll interval: {poll_interval}s)... Press Ctrl+C to stop.\n"
    )
    out.flush()

    rt: Runtime = runtime_factory() if runtime_factory is not None else Runtime.from_settings()
    app = create_app(rt, token=token, host=host)

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _stop_all() -> None:
        server.should_exit = True
        rt.scheduler.stop()
        rt.stop()

    if hasattr(rt.office, "_stop_event"):
        def _watch_stop() -> None:
            rt.office._stop_event.wait()
            server.should_exit = True

        watch_thread = threading.Thread(target=_watch_stop, daemon=True)
        watch_thread.start()

    rt.start()
    scheduler_thread = threading.Thread(target=rt.scheduler.run, daemon=True)
    scheduler_thread.start()

    try:
        server.run()
    except KeyboardInterrupt:
        out.write("\nStopping Agent Office...\n")
    finally:
        _stop_all()
        scheduler_thread.join(timeout=1.0)

    return 0


def _cmd_task(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    ticker = args.ticker.upper().strip()
    agent = args.agent.strip()
    reason = args.reason.strip()
    when_ts = args.when.strip() if args.when else None

    res = client.command(
        "enqueue_task",
        {"agent": agent, "ticker": ticker, "reason": reason, "when_ts": when_ts},
    )
    if not res.ok:
        out.write(f"Task enqueue failed: {res.reasons}\n")
        return 1

    task_id = res.data.get("task_id")
    due = res.data.get("due", when_ts)
    out.write(f"Enqueued manual task #{task_id} for {agent} on {ticker} (due: {due})\n")
    return 0


def _cmd_say(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    agent = args.agent.strip()
    chat = args.chat.strip()
    text = args.text.strip()

    res = client.command("say", {"agent": agent, "chat": chat, "text": text})
    if not res.ok:
        out.write(f"Say failed: {res.reasons}\n")
        return 1

    msg_id = res.data.get("message_id")
    out.write(f"Message #{msg_id} appended to chat '{chat}' ({agent})\n")
    if "task_id" in res.data:
        task_id = res.data["task_id"]
        out.write(f"Enqueued manual task #{task_id} for PM on {chat.upper()}\n")

    return 0


def _cmd_cycles_list(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    rows = client.read("cycles", {"ticker": args.ticker, "limit": args.limit})
    if getattr(args, "json", False):
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


def _cmd_cycles_show(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    cycle_id = args.cycle_id
    try:
        cycle = client.read("cycle", {"cycle_id": cycle_id})
    except Exception:
        out.write(f"Cycle #{cycle_id} not found.\n")
        return 1

    if getattr(args, "json", False):
        out.write(json.dumps(cycle, indent=2) + "\n")
        return 0

    out.write(f"Cycle #{cycle['id']} on {cycle['ticker']}:\n")
    out.write(f"  Status:  {cycle['status']}\n")
    out.write(f"  Opened:  {cycle['opened_ts']}\n")
    out.write(f"  Closed:  {cycle.get('closed_ts') or '-'}\n")
    out.write(f"  Outcome: {cycle.get('outcome') or '-'}\n")

    budget_used = cycle.get("budget_used", {})
    out.write(
        f"  Budget:  messages={budget_used.get('messages', 0)}, "
        f"subagents={budget_used.get('subagents', 0)}, total={budget_used.get('total', 0)}\n"
    )

    messages = cycle.get("messages", [])
    out.write(f"\nMessages ({len(messages)}):\n")
    if messages:
        headers = ["ID", "AUTHOR", "TIMESTAMP", "TEXT"]
        rows = [[m["id"], m["author"], m["ts"], m["text"][:80]] for m in messages]
        out.write(_format_table(headers, rows) + "\n")
    else:
        out.write("  No messages in this cycle.\n")

    return 0


def _cmd_chat_show(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    agent = args.agent.strip()
    topic = args.topic.strip()
    messages = client.read("chat", {"agent": agent, "topic": topic, "limit": args.limit})

    if getattr(args, "json", False):
        out.write(json.dumps(messages, indent=2) + "\n")
        return 0

    out.write(f"Chat '{topic}' for agent '{agent}' ({len(messages)} messages):\n")
    if messages:
        headers = ["ID", "AUTHOR", "TIMESTAMP", "KIND", "TEXT"]
        rows = [
            [m["id"], m["author"], m["ts"], m["kind"], m["text"][:80]]
            for m in messages
        ]
        out.write(_format_table(headers, rows) + "\n")
    else:
        out.write("  Chat is empty.\n")
    return 0


def _cmd_state_show(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    ticker = args.ticker.upper().strip()
    state_data = client.read("ticker_state", {"ticker": ticker})

    if not state_data:
        out.write(f"No state found for {ticker}.\n")
        return 0

    if getattr(args, "json", False):
        out.write(json.dumps(state_data, indent=2) + "\n")
    else:
        out.write(f"Ticker state for {ticker}:\n")
        out.write(str(state_data) + "\n")
    return 0


def _cmd_watchlist_list(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    items = client.read("watchlist")
    if getattr(args, "json", False):
        out.write(json.dumps(items, indent=2) + "\n")
        return 0

    headers = ["TICKER", "ADDED_TS", "NOTE"]
    rows = [[it["ticker"], it["added_ts"], it.get("note") or ""] for it in items]
    out.write(_format_table(headers, rows) + "\n")
    return 0


def _cmd_watchlist_add(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    ticker = args.ticker.upper().strip()
    note = getattr(args, "note", "") or ""
    res = client.command("add_watchlist", {"ticker": ticker, "note": note})
    if res.ok:
        out.write(f"Added {ticker} to watchlist.\n")
        return 0
    out.write(f"Failed to add {ticker} to watchlist: {res.reasons}\n")
    return 1


def _cmd_watchlist_remove(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    ticker = args.ticker.upper().strip()
    res = client.command("remove_watchlist", {"ticker": ticker})
    if res.ok:
        out.write(f"Removed {ticker} from watchlist.\n")
        return 0
    out.write(f"Ticker {ticker} was not in watchlist.\n")
    return 0


def _cmd_orders_list(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    rows = client.read("orders", {"ticker": args.ticker, "status": args.status, "limit": args.limit})
    if getattr(args, "json", False):
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


def _cmd_orders_approve(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    order_id = args.order_id
    res = client.command("approve_order", {"order_id": order_id, "confirm": True})
    if res.ok:
        out.write(f"Order #{order_id} approved successfully: status={res.data.get('status')}\n")
        return 0
    else:
        out.write(
            f"Order #{order_id} approval failed / deferred: "
            f"status={res.data.get('status')}, reasons={res.reasons}\n"
        )
        return 1


def _cmd_orders_reject(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    order_id = args.order_id
    reason = getattr(args, "reason", "User rejected via CLI")
    res = client.command("reject_order", {"order_id": order_id, "reason": reason})
    out.write(f"Order #{order_id} rejected: {tuple(res.reasons)}\n")
    return 0


def _cmd_orders_sync(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    res = client.command("reconcile_broker")
    orders_synced = res.data.get("orders_synced", 0)
    out.write(f"Synced with broker: {orders_synced} order(s) updated []\n")
    return 0


def _cmd_trades_list(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    ticker = args.ticker.upper().strip() if args.ticker else None
    open_only = getattr(args, "open_only", False)
    status = "open" if open_only else None

    trades = client.read("trades", {"ticker": ticker, "status": status})
    if getattr(args, "json", False):
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


def _cmd_portfolio_sync(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    res = client.command("reconcile_broker")
    if not res.ok:
        out.write(f"Portfolio sync failed: {res.reasons}\n")
        return 1

    p = client.read("portfolio")
    if not p:
        out.write("No portfolio data returned.\n")
        return 1

    now_ts = p.get("ts", "")
    equity = float(p.get("equity", 0.0))
    cash = float(p.get("cash", 0.0))
    positions = p.get("positions", [])

    if getattr(args, "json", False):
        out.write(json.dumps(p, indent=2) + "\n")
        return 0

    out.write(f"Portfolio synchronized at {now_ts}:\n")
    out.write(f"  Equity:    ${equity:,.2f}\n")
    out.write(f"  Cash:      ${cash:,.2f}\n")
    out.write(f"  Positions: {len(positions)}\n")
    for pos in positions:
        sym = pos.get("symbol", "")
        qty = pos.get("quantity", 0)
        mv = pos.get("market_value", 0.0)
        out.write(f"    - {sym}: {qty} shares (${float(mv):,.2f})\n")
    return 0


def _cmd_data_refresh(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    kinds = args.kinds.split(",") if getattr(args, "kinds", None) else None
    force = getattr(args, "force", False)
    res = client.command("refresh_data", {"force": force, "kinds": kinds})
    count = res.data.get("count", 0)
    out.write(f"Data refresh completed: {count} items processed.\n")
    return 0


def _cmd_inbox(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    mark_read = getattr(args, "mark_read", None)
    if mark_read is not None:
        client.command("mark_inbox_read", {"item_id": mark_read})
        out.write(f"Marked inbox item #{mark_read} as read.\n")
        return 0

    unread_only = getattr(args, "unread_only", False)
    limit = getattr(args, "limit", 50)
    items = client.read("inbox", {"unread_only": unread_only, "limit": limit})

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


def _cmd_halt(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    cancel_open = getattr(args, "cancel_open", True)
    client.command("halt", {"cancel_open": cancel_open, "confirm": True})
    out.write(f"System halted. Trading stopped (cancel_open={cancel_open}).\n")
    return 0


def _cmd_resume(client: RuntimeClient, args: argparse.Namespace, out: TextIO) -> int:
    client.command("resume", {"confirm": True})
    out.write("System resumed. Trading allowed.\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading-agent",
        description="Autonomous Agent Office CLI",
    )
    parser.add_argument(
        "--runtime",
        dest="runtime_url",
        default=None,
        help="Runtime base URL (default: http://127.0.0.1:8765 or TRADING_AGENT_RUNTIME_URL)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. run
    p_run = subparsers.add_parser("run", help="Run the Agent Office scheduler loop")
    p_run.add_argument("--poll-interval", type=float, default=0.5, help="Poll interval in seconds")
    p_run.add_argument("--host", default=None, help="Host to bind API")
    p_run.add_argument("--port", type=int, default=None, help="Port to bind API")
    p_run.add_argument("--token", default=None, help="Bearer token for API auth")
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
    sp_ch_show.add_argument("topic", help="Chat topic (ticker or theme)")
    sp_ch_show.add_argument("--limit", type=int, default=50, help="Max messages")
    sp_ch_show.add_argument("--json", action="store_true", help="Output JSON")
    sp_ch_show.set_defaults(handler=_cmd_chat_show)

    # 6. state
    p_state = subparsers.add_parser("state", help="Inspect ticker state")
    sp_state = p_state.add_subparsers(dest="subcommand", required=True)

    sp_st_show = sp_state.add_parser("show", help="Show current state for a ticker")
    sp_st_show.add_argument("ticker", help="Ticker symbol")
    sp_st_show.add_argument("--json", action="store_true", help="Output JSON")
    sp_st_show.set_defaults(handler=_cmd_state_show)

    # 7. watchlist
    p_wl = subparsers.add_parser("watchlist", help="Manage watchlist tickers")
    sp_wl = p_wl.add_subparsers(dest="subcommand", required=True)

    sp_wl_list = sp_wl.add_parser("list", help="List watchlist tickers")
    sp_wl_list.add_argument("--json", action="store_true", help="Output JSON")
    sp_wl_list.set_defaults(handler=_cmd_watchlist_list)

    sp_wl_add = sp_wl.add_parser("add", help="Add ticker to watchlist")
    sp_wl_add.add_argument("ticker", help="Ticker symbol")
    sp_wl_add.add_argument("--note", default="", help="Optional note")
    sp_wl_add.set_defaults(handler=_cmd_watchlist_add)

    sp_wl_rem = sp_wl.add_parser("remove", help="Remove ticker from watchlist")
    sp_wl_rem.add_argument("ticker", help="Ticker symbol")
    sp_wl_rem.set_defaults(handler=_cmd_watchlist_remove)

    # 8. orders
    p_ord = subparsers.add_parser("orders", help="Inspect and manage orders")
    sp_ord = p_ord.add_subparsers(dest="subcommand", required=True)

    sp_ord_list = sp_ord.add_parser("list", help="List orders")
    sp_ord_list.add_argument("--ticker", default=None, help="Filter by ticker")
    sp_ord_list.add_argument("--status", default=None, help="Filter by status")
    sp_ord_list.add_argument("--limit", type=int, default=20, help="Max entries")
    sp_ord_list.add_argument("--json", action="store_true", help="Output JSON")
    sp_ord_list.set_defaults(handler=_cmd_orders_list)

    sp_ord_app = sp_ord.add_parser("approve", help="Approve a pending order")
    sp_ord_app.add_argument("order_id", type=int, help="Order ID to approve")
    sp_ord_app.set_defaults(handler=_cmd_orders_approve)

    sp_ord_rej = sp_ord.add_parser("reject", help="Reject a pending order")
    sp_ord_rej.add_argument("order_id", type=int, help="Order ID to reject")
    sp_ord_rej.add_argument("--reason", default="User rejected via CLI", help="Rejection reason")
    sp_ord_rej.set_defaults(handler=_cmd_orders_reject)

    sp_ord_sync = sp_ord.add_parser("sync", help="Synchronize orders with broker")
    sp_ord_sync.set_defaults(handler=_cmd_orders_sync)

    # 9. trades
    p_tr = subparsers.add_parser("trades", help="Inspect trades")
    sp_tr = p_tr.add_subparsers(dest="subcommand", required=True)

    sp_tr_list = sp_tr.add_parser("list", help="List trades")
    sp_tr_list.add_argument("--ticker", default=None, help="Filter by ticker")
    sp_tr_list.add_argument("--open-only", action="store_true", help="Only open trades")
    sp_tr_list.add_argument("--limit", type=int, default=50, help="Max entries")
    sp_tr_list.add_argument("--json", action="store_true", help="Output JSON")
    sp_tr_list.set_defaults(handler=_cmd_trades_list)

    # 10. portfolio
    p_port = subparsers.add_parser("portfolio", help="Inspect portfolio")
    sp_port = p_port.add_subparsers(dest="subcommand", required=True)

    sp_p_sync = sp_port.add_parser("sync", help="Sync portfolio snapshot from broker")
    sp_p_sync.add_argument("--json", action="store_true", help="Output JSON")
    sp_p_sync.set_defaults(handler=_cmd_portfolio_sync)

    # 11. data
    p_data = subparsers.add_parser("data", help="Data cache operations")
    sp_data = p_data.add_subparsers(dest="subcommand", required=True)

    sp_d_ref = sp_data.add_parser("refresh", help="Trigger data pre-fetch refresh")
    sp_d_ref.add_argument("--force", action="store_true", help="Force refresh even if not stale")
    sp_d_ref.add_argument("--kinds", default=None, help="Comma-separated data kinds")
    sp_d_ref.set_defaults(handler=_cmd_data_refresh)

    # 12. inbox
    p_inbox = subparsers.add_parser("inbox", help="View and manage system inbox")
    p_inbox.add_argument("--unread-only", action="store_true", help="Show only unread items")
    p_inbox.add_argument("--limit", type=int, default=50, help="Max items")
    p_inbox.add_argument("--mark-read", type=int, default=None, help="Mark item ID as read")
    p_inbox.add_argument("--json", action="store_true", help="Output JSON")
    p_inbox.set_defaults(handler=_cmd_inbox)

    # 13. halt & resume
    p_halt = subparsers.add_parser("halt", help="Emergency halt: stop all trading")
    p_halt.add_argument("--no-cancel-open", dest="cancel_open", action="store_false", default=True)
    p_halt.set_defaults(handler=_cmd_halt)

    p_resume = subparsers.add_parser("resume", help="Resume trading after halt")
    p_resume.set_defaults(handler=_cmd_resume)

    # 14. config check
    p_cfg = subparsers.add_parser("config", help="Configuration utilities")
    sp_cfg = p_cfg.add_subparsers(dest="subcommand", required=True)
    sp_cfg_chk = sp_cfg.add_parser("check", help="Verify configuration validity")
    sp_cfg_chk.add_argument("--json", action="store_true", help="Output JSON")

    return parser


def main(
    argv: Sequence[str] | None = None,
    client_factory: Callable[[], RuntimeClient] | None = None,
    runtime_factory: Callable[[], Any] | None = None,
    office_factory: Callable[[], Any] | None = None,
    out: TextIO | None = None,
) -> int:
    """CLI entrypoint. Returns exit code (0 on success, non-zero on failure)."""
    out = out or sys.stdout
    parser = build_parser()

    subcmds = (
        "run", "task", "say", "cycles", "chat", "state", "watchlist",
        "orders", "trades", "portfolio", "data", "inbox", "halt", "resume", "config",
    )
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    if any(a in ("-h", "--help") for a in raw_args) and not any(a in subcmds for a in raw_args):
        parser.print_help(out)
        return 0

    try:
        args = parser.parse_args(raw_args)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    cmd_name = getattr(args, "command", "")
    sub_name = getattr(args, "subcommand", None)

    # Local command: config check (no Runtime, no DB needed)
    if cmd_name == "config" and sub_name == "check":
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

    # Command: run (launches the Runtime server)
    if cmd_name == "run":
        factory = runtime_factory or office_factory
        return _cmd_run(factory, args, out)

    # All other commands use RuntimeClient
    base_url = (
        getattr(args, "runtime_url", None)
        or os.environ.get("TRADING_AGENT_RUNTIME_URL")
        or "http://127.0.0.1:8765"
    )
    token = os.environ.get("TRADING_AGENT_API_TOKEN")

    client = (
        client_factory()
        if client_factory is not None
        else RuntimeClient(base_url=base_url, token=token)
    )

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(out)
        return 1

    try:
        return handler(client, args, out)
    except RuntimeUnavailable as exc:
        out.write(f"{exc}\n")
        return 2
    except Exception as exc:
        out.write(f"Command execution error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
