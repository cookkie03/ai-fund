"""Read model del Portafoglio: posizioni, allocazione, performance, attribuzione, uso dei limiti.

Funzioni che leggono da una connessione SQLite (anche read-only) e restituiscono i dict del
contratto in `docs/dashboard.md`. Importi in valuta del conto, percentuali come frazioni,
timestamp ISO UTC. Nessuna scrittura.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from analysis.portfolio_metrics import TradeStat, compute_performance, period_start

UNKNOWN_SECTOR = "Unknown"
NEAR_FRACTION = 0.8  # "near" oltre l'80% della soglia


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def latest_snapshot(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM portfolio_snapshots ORDER BY ts DESC LIMIT 1").fetchone()
    if not row:
        return None
    return {
        "ts": row["ts"],
        "equity": float(row["equity"]),
        "cash": float(row["cash"]),
        "positions": json.loads(row["positions_json"] or "[]"),
    }


def sector_map(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        rows = conn.execute("SELECT symbol, sector FROM securities").fetchall()
    except sqlite3.Error:
        return {}
    return {r["symbol"].upper(): r["sector"] for r in rows if r["sector"]}


def is_halted(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute("SELECT value FROM system_state WHERE key = 'halted'").fetchone()
    except sqlite3.Error:
        return False
    return bool(row and row["value"] == "1")


def _snapshot_position(p: Any) -> dict[str, Any] | None:
    get = p.get if isinstance(p, dict) else lambda k, d=None: getattr(p, k, d)
    sym = str(get("symbol", "") or "").upper()
    if not sym:
        return None
    qty = float(get("qty", get("quantity", 0)) or 0)
    mv = get("market_value")
    cp = get("current_price")
    if cp is None and mv is not None and qty:
        cp = float(mv) / qty
    entry = get("avg_entry_price")
    if entry is None and get("cost_basis") and qty:
        entry = float(get("cost_basis")) / qty
    return {
        "symbol": sym,
        "qty": qty,
        "current_price": float(cp) if cp is not None else None,
        "entry": float(entry) if entry is not None else None,
    }


def _last_close(conn: sqlite3.Connection, symbol: str) -> float | None:
    try:
        row = conn.execute(
            "SELECT c FROM prices_ohlcv WHERE symbol = ? AND interval = '1d' "
            "ORDER BY ts DESC LIMIT 1",
            (symbol,),
        ).fetchone()
    except sqlite3.Error:
        return None
    return float(row["c"]) if row else None


def _draft_levels(conn: sqlite3.Connection, order_id: int) -> tuple[float | None, float | None]:
    row = conn.execute("SELECT draft_json FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        return None, None
    try:
        d = json.loads(row["draft_json"])
    except (TypeError, ValueError):
        return None, None
    stop = float(d["stop"]) if d.get("stop") else None
    tp = float(d["take_profit"]) if d.get("take_profit") else None
    return stop, tp


def trade_levels(conn: sqlite3.Connection, trade: sqlite3.Row) -> tuple[float | None, float | None]:
    """Stop e target correnti: colonne del trade, altrimenti bozza dell'ordine / eventi."""
    keys = trade.keys()
    stop = trade["stop_price"] if "stop_price" in keys else None
    target = trade["target_price"] if "target_price" in keys else None
    if stop is None or target is None:
        d_stop, d_tp = _draft_levels(conn, int(trade["entry_order_id"]))
        stop = stop if stop is not None else d_stop
        target = target if target is not None else d_tp
        if stop is not None:
            for ev in json.loads(trade["events_json"] or "[]"):
                if ev.get("new_stop"):
                    stop = float(ev["new_stop"])
                elif ev.get("stop") and ev.get("event") == "trail_armed":
                    stop = float(ev["stop"])
    return (float(stop) if stop is not None else None, float(target) if target is not None else None)


def _closed_after(conn: sqlite3.Connection, ticker: str, snapshot_ts: str) -> bool:
    snap_dt = _parse(snapshot_ts)
    for r in conn.execute(
        "SELECT closed_ts FROM trades WHERE ticker = ? AND closed_ts IS NOT NULL", (ticker,)
    ).fetchall():
        closed = _parse(r["closed_ts"])
        if closed and snap_dt and closed > snap_dt:
            return True
    return False


def open_positions(conn: sqlite3.Connection, now: datetime) -> list[dict[str, Any]]:
    """Posizioni aperte: trade aperti uniti ai prezzi dell'ultima fotografia del portafoglio."""
    snap = latest_snapshot(conn)
    equity = snap["equity"] if snap else 0.0
    snap_pos = {}
    for p in (snap["positions"] if snap else []):
        sp = _snapshot_position(p)
        if sp:
            snap_pos[sp["symbol"]] = sp
    sectors = sector_map(conn)
    trades = conn.execute(
        "SELECT * FROM trades WHERE closed_ts IS NULL ORDER BY opened_ts ASC, id ASC"
    ).fetchall()
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def build(
        ticker: str,
        qty: float,
        entry: float,
        price: float,
        stop: float | None,
        target: float | None,
        trade: sqlite3.Row | None,
    ) -> dict[str, Any]:
        value = qty * price
        open_risk = max(price - stop, 0.0) * qty if stop is not None else None
        opened = _parse(trade["opened_ts"]) if trade is not None else None
        return {
            "ticker": ticker,
            "side": "long",
            "qty": qty,
            "avg_entry_price": entry,
            "current_price": price,
            "market_value": value,
            "weight": value / equity if equity else 0.0,
            "unrealized_pnl": (price - entry) * qty,
            "unrealized_pnl_fraction": price / entry - 1.0 if entry else 0.0,
            "stop_price": stop,
            "target_price": target,
            "open_risk": open_risk,
            "open_risk_fraction": (open_risk / equity) if open_risk is not None and equity else None,
            "sector": sectors.get(ticker, UNKNOWN_SECTOR),
            "opened_ts": trade["opened_ts"] if trade is not None else None,
            "days_held": (now - opened).days if opened else None,
            "trade_id": int(trade["id"]) if trade is not None else None,
            "proposed_by": (trade["proposed_by"] if trade is not None else None),
        }

    for t in trades:
        ticker = t["ticker"].upper()
        remaining = float(t["qty"]) - float(t["closed_qty"] or 0.0)
        if remaining <= 1e-9:
            continue
        sp = snap_pos.get(ticker)
        price = (sp or {}).get("current_price") or _last_close(conn, ticker)
        price = price if price is not None else float(t["entry_price"])
        stop, target = trade_levels(conn, t)
        seen.add(ticker)
        out.append(build(ticker, remaining, float(t["entry_price"]), price, stop, target, t))

    for ticker, sp in snap_pos.items():  # posizioni del broker senza trade locale (riconciliate)
        if ticker in seen or sp["qty"] <= 0:
            continue
        if _closed_after(conn, ticker, snap["ts"]):
            continue  # la fotografia è precedente alla chiusura: non è più una posizione
        price = sp["current_price"] if sp["current_price"] is not None else (sp["entry"] or 0.0)
        out.append(build(ticker, sp["qty"], sp["entry"] or price, price, None, None, None))
    return out


def current_price(conn: sqlite3.Connection, ticker: str) -> float | None:
    snap = latest_snapshot(conn)
    for p in (snap["positions"] if snap else []):
        sp = _snapshot_position(p)
        if sp and sp["symbol"] == ticker.upper() and sp["current_price"] is not None:
            return sp["current_price"]
    return _last_close(conn, ticker.upper())


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def trade_pnl(t: sqlite3.Row) -> float | None:
    """PnL realizzato di un trade chiuso (parziali incluse); fallback per righe precedenti."""
    if t["realized_pnl"] is not None:
        return float(t["realized_pnl"])
    if t["exit_price"] is None:
        return None
    return (float(t["exit_price"]) - float(t["entry_price"])) * float(t["qty"])


def trade_r_multiple(t: sqlite3.Row, pnl: float | None) -> float | None:
    stop = t["initial_stop"] if "initial_stop" in t.keys() else None
    if pnl is None or stop is None:
        return None
    risk = (float(t["entry_price"]) - float(stop)) * float(t["qty"])
    return pnl / risk if risk > 0 else None


def _partials(t: sqlite3.Row) -> list[tuple[str, float]]:
    """(ts, PnL) di ogni chiusura parziale del trade."""
    return [
        (e.get("ts") or "", (float(e["price"]) - float(t["entry_price"])) * float(e["qty"]))
        for e in json.loads(t["events_json"] or "[]")
        if e.get("event") == "partial_exit"
    ]


def realized_today(conn: sqlite3.Connection, now: datetime) -> float:
    """PnL realizzato dalla mezzanotte UTC: trade chiusi oggi (al netto delle parziali di
    giorni precedenti) più le parziali di oggi sui trade ancora aperti."""
    start = iso(_day_start(now)) or ""
    total = 0.0
    for t in conn.execute("SELECT * FROM trades WHERE closed_ts >= ?", (start,)).fetchall():
        total += (trade_pnl(t) or 0.0) - sum(pnl for ts, pnl in _partials(t) if ts < start)
    for t in conn.execute("SELECT * FROM trades WHERE closed_ts IS NULL AND closed_qty > 0"):
        total += sum(pnl for ts, pnl in _partials(t) if ts >= start)
    return total


def portfolio_summary(conn: sqlite3.Connection, now: datetime, limits: dict[str, Any]) -> dict:
    snap = latest_snapshot(conn)
    positions = open_positions(conn, now)
    invested = sum(p["market_value"] for p in positions)
    unrealized = sum(p["unrealized_pnl"] for p in positions)
    if snap is None:
        return {
            "ts": None, "equity": 0.0, "cash": 0.0, "invested": invested,
            "cash_reserve_fraction": 0.0, "day_change": 0.0, "day_change_fraction": 0.0,
            "unrealized_pnl": unrealized, "realized_pnl_today": realized_today(conn, now),
            "positions_count": len(positions), "snapshot_age_s": None,
            "halted": is_halted(conn),
        }
    start = iso(_day_start(now)) or ""
    prev = conn.execute(
        "SELECT equity FROM portfolio_snapshots WHERE ts < ? ORDER BY ts DESC LIMIT 1", (start,)
    ).fetchone()
    base = float(prev["equity"]) if prev else None
    if base is None:
        first = conn.execute(
            "SELECT equity FROM portfolio_snapshots WHERE ts >= ? ORDER BY ts ASC LIMIT 1", (start,)
        ).fetchone()
        base = float(first["equity"]) if first else snap["equity"]
    change = snap["equity"] - base
    ts = _parse(snap["ts"])
    return {
        "ts": snap["ts"],
        "equity": snap["equity"],
        "cash": snap["cash"],
        "invested": invested,
        "cash_reserve_fraction": snap["cash"] / snap["equity"] if snap["equity"] else 0.0,
        "day_change": change,
        "day_change_fraction": change / base if base else 0.0,
        "unrealized_pnl": unrealized,
        "realized_pnl_today": realized_today(conn, now),
        "positions_count": len(positions),
        "snapshot_age_s": max((now - ts).total_seconds(), 0.0) if ts else None,
        "halted": is_halted(conn),
    }


def allocation(conn: sqlite3.Connection, now: datetime, limits: dict[str, Any]) -> dict:
    snap = latest_snapshot(conn)
    equity = snap["equity"] if snap else 0.0
    cash = snap["cash"] if snap else 0.0
    positions = open_positions(conn, now)
    by_sector: dict[str, float] = defaultdict(float)
    for p in positions:
        by_sector[p["sector"]] += p["market_value"]
    return {
        "by_sector": [
            {"sector": s, "value": v, "weight": v / equity if equity else 0.0,
             "limit": limits["max_sector_fraction"]}
            for s, v in sorted(by_sector.items(), key=lambda kv: -kv[1])
        ],
        "by_position": [
            {"ticker": p["ticker"], "value": p["market_value"], "weight": p["weight"],
             "limit": limits["max_position_fraction"]}
            for p in sorted(positions, key=lambda p: -p["market_value"])
        ],
        "cash": {
            "value": cash,
            "weight": cash / equity if equity else 0.0,
            "min_reserve": limits["min_cash_reserve_fraction"],
        },
    }


def _status(current: float, threshold: float, *, minimum: bool = False) -> str:
    if minimum:
        if current < threshold:
            return "breach"
        return "near" if current > 0 and threshold / current > NEAR_FRACTION else "ok"
    if current > threshold:
        return "breach"
    return "near" if threshold > 0 and current / threshold > NEAR_FRACTION else "ok"


def limits_usage(conn: sqlite3.Connection, now: datetime, limits: dict[str, Any]) -> list[dict]:
    snap = latest_snapshot(conn)
    equity = snap["equity"] if snap else 0.0
    cash = snap["cash"] if snap else 0.0
    positions = open_positions(conn, now)
    usage: list[dict[str, Any]] = []

    def add(name: str, current: float, minimum: bool, detail: str) -> None:
        threshold = float(limits[name])
        usage.append({"limit": name, "current": current, "threshold": threshold,
                      "status": _status(current, threshold, minimum=minimum), "detail": detail})

    top = max(positions, key=lambda p: p["weight"], default=None)
    add("max_position_fraction", top["weight"] if top else 0.0, False,
        f"Posizione maggiore: {top['ticker']}" if top else "Nessuna posizione aperta")
    sectors: dict[str, float] = defaultdict(float)
    for p in positions:
        sectors[p["sector"]] += p["weight"]
    s_top = max(sectors.items(), key=lambda kv: kv[1], default=None)
    add("max_sector_fraction", s_top[1] if s_top else 0.0, False,
        f"Settore maggiore: {s_top[0]}" if s_top else "Nessuna posizione aperta")
    add("max_open_positions", float(len(positions)), False, f"{len(positions)} posizioni aperte")
    reserve = cash / equity if equity else 0.0
    add("min_cash_reserve_fraction", reserve, True, f"Liquidità {cash:.2f} su equity {equity:.2f}")
    risky = [p for p in positions if p["open_risk_fraction"] is not None]
    r_top = max(risky, key=lambda p: p["open_risk_fraction"], default=None)
    add("max_risk_per_trade_fraction", r_top["open_risk_fraction"] if r_top else 0.0, False,
        f"Rischio aperto maggiore: {r_top['ticker']}" if r_top else "Nessuno stop impostato")
    rr: list[tuple[float, str]] = []
    for t in conn.execute("SELECT * FROM trades WHERE closed_ts IS NULL").fetchall():
        stop = t["initial_stop"] if t["initial_stop"] is not None else t["stop_price"]
        _, target = trade_levels(conn, t)
        if stop is not None and target is not None and t["entry_price"] > stop:
            rr.append(((target - t["entry_price"]) / (t["entry_price"] - stop), t["ticker"]))
    worst = min(rr, default=None)
    add("min_risk_reward_ratio", worst[0] if worst else float(limits["min_risk_reward_ratio"]),
        True, f"R:R più basso all'ingresso: {worst[1]}" if worst else "Nessun trade con stop e target")
    return usage


def _closed_trades(conn: sqlite3.Connection, start: datetime | None) -> list[sqlite3.Row]:
    if start is None:
        return conn.execute("SELECT * FROM trades WHERE closed_ts IS NOT NULL").fetchall()
    return conn.execute(
        "SELECT * FROM trades WHERE closed_ts IS NOT NULL AND closed_ts >= ?", (iso(start),)
    ).fetchall()


def _equity_window(conn: sqlite3.Connection, start: datetime | None) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    if start is not None:
        base = conn.execute(
            "SELECT ts, equity FROM portfolio_snapshots WHERE ts <= ? ORDER BY ts DESC LIMIT 1",
            (iso(start),),
        ).fetchone()
        if base:
            rows.append((base["ts"], float(base["equity"])))
        q = conn.execute(
            "SELECT ts, equity FROM portfolio_snapshots WHERE ts > ? ORDER BY ts ASC", (iso(start),)
        ).fetchall()
    else:
        q = conn.execute("SELECT ts, equity FROM portfolio_snapshots ORDER BY ts ASC").fetchall()
    rows.extend((r["ts"], float(r["equity"])) for r in q)
    return rows


def _benchmark_points(
    conn: sqlite3.Connection, ticker: str, start: datetime | None
) -> list[tuple[str, float]]:
    sql = "SELECT ts, c FROM prices_ohlcv WHERE symbol = ? AND interval = '1d'"
    params: list[Any] = [ticker.upper()]
    if start is not None:
        sql += " AND ts >= ?"
        params.append(iso(start))
    sql += " ORDER BY ts ASC"
    try:
        return [(r["ts"], float(r["c"])) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.Error:
        return []


def performance(
    conn: sqlite3.Connection, now: datetime, period: str, benchmark: str | None = "SPY"
) -> dict[str, Any]:
    start = period_start(period, now)
    points = _equity_window(conn, start)
    stats = []
    for t in _closed_trades(conn, start):
        pnl = trade_pnl(t)
        if pnl is not None:
            stats.append(TradeStat(pnl=pnl, r_multiple=trade_r_multiple(t, pnl)))
    bench = None
    if benchmark:
        bench = (benchmark.upper(), _benchmark_points(conn, benchmark, start))
    perf = compute_performance(points, stats, benchmark=bench)
    positions = open_positions(conn, now)
    return {
        "period": period.upper(),
        "from": points[0][0] if points else iso(start),
        "to": points[-1][0] if points else iso(now),
        "observations": perf.pop("observations"),
        "return_fraction": perf.pop("return_fraction"),
        "realized_pnl": perf.pop("realized_pnl"),
        "unrealized_pnl": sum(p["unrealized_pnl"] for p in positions),
        **perf,
    }


def attribution(conn: sqlite3.Connection, now: datetime, period: str) -> dict[str, Any]:
    start = period_start(period, now)
    points = _equity_window(conn, start)
    base = points[0][1] if points else None
    sectors = sector_map(conn)
    by_pos: dict[str, float] = defaultdict(float)
    by_sector: dict[str, float] = defaultdict(float)
    by_agent: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])

    for t in _closed_trades(conn, start):
        pnl = trade_pnl(t)
        if pnl is None:
            continue
        ticker = t["ticker"].upper()
        by_pos[ticker] += pnl
        by_sector[sectors.get(ticker, UNKNOWN_SECTOR)] += pnl
        agent = t["proposed_by"] or "unknown"
        by_agent[agent][0] += pnl
        by_agent[agent][1] += 1
    for p in open_positions(conn, now):
        by_pos[p["ticker"]] += p["unrealized_pnl"]
        by_sector[p["sector"]] += p["unrealized_pnl"]
        agent = p["proposed_by"] or "unknown"
        by_agent[agent][0] += p["unrealized_pnl"]
        by_agent[agent][1] += 1

    def frac(pnl: float) -> float | None:
        return pnl / base if base else None

    def rows(d: dict[str, float], key: str) -> list[dict[str, Any]]:
        return [
            {key: k, "pnl": v, "contribution_fraction": frac(v)}
            for k, v in sorted(d.items(), key=lambda kv: -kv[1])
        ]

    return {
        "by_position": rows(by_pos, "ticker"),
        "by_sector": rows(by_sector, "sector"),
        "by_agent": [
            {"agent": a, "pnl": v[0], "contribution_fraction": frac(v[0]), "trades": int(v[1])}
            for a, v in sorted(by_agent.items(), key=lambda kv: -kv[1][0])
        ],
    }


def equity_history_with_drawdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggiunge `drawdown_fraction` (equity / massimo storico - 1) a ogni punto."""
    peak = 0.0
    out = []
    for r in rows:
        peak = max(peak, float(r["equity"]))
        out.append({**r, "drawdown_fraction": float(r["equity"]) / peak - 1.0 if peak else 0.0})
    return out
