"""Synthetic office scenario for the Cockpit dev server (development only, never production).

Generates NYSE-session OHLCV bars (15m, aggregated to 1h and 1d) with a seeded random walk
per ticker, and seeds watchlist, chart annotations signed by agents and by Luca, orders in
every lifecycle state, open and closed trades, portfolio snapshots, ticker state, cycles,
chats and inbox items, so every state of the Terminale can be exercised.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from tests.workflows.test_office import FakeMarketData

ET = ZoneInfo("America/New_York")

# ticker -> (last price anchor, daily vol, drift per day, base 15m volume)
_PROFILE: dict[str, tuple[float, float, float, int]] = {
    "AAPL": (229.0, 0.013, 0.0006, 1_150_000),
    "NVDA": (181.0, 0.024, 0.0011, 4_800_000),
    "MSFT": (471.0, 0.012, 0.0003, 520_000),
    "AMD": (157.0, 0.027, -0.0004, 1_900_000),
    "JPM": (246.0, 0.011, 0.0004, 310_000),
    "XOM": (117.0, 0.012, -0.0002, 480_000),
    "LLY": (812.0, 0.017, 0.0008, 140_000),
    "TSLA": (342.0, 0.031, 0.0002, 2_700_000),
    "GOOGL": (284.0, 0.016, 0.0007, 900_000),
    "META": (618.0, 0.019, 0.0005, 450_000),
    "AMZN": (226.0, 0.017, 0.0004, 1_300_000),
}

_SESSION_DAYS = 160


def _trading_days(end: date, count: int) -> list[date]:
    days: list[date] = []
    d = end
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def _last_session_end(now: datetime) -> tuple[date, datetime]:
    """Last session day and the cut-off time of available bars (ET)."""
    local = now.astimezone(ET)
    d = local.date()
    open_dt = datetime.combine(d, time(9, 30), ET)
    close_dt = datetime.combine(d, time(16, 0), ET)
    if d.weekday() < 5 and local >= open_dt:
        return d, min(local, close_dt)
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d, datetime.combine(d, time(16, 0), ET)


class ScenarioMarketData(FakeMarketData):
    """FakeMarketData with realistic, deterministic NYSE-session bars."""

    def __init__(self, now: datetime | None = None) -> None:
        super().__init__()
        self._now = now or datetime.now(UTC)
        self._bars15: dict[str, list[dict[str, Any]]] = {}
        self._quotes = {}

    def _generate(self, symbol: str) -> list[dict[str, Any]]:
        if symbol in self._bars15:
            return self._bars15[symbol]
        if symbol not in _PROFILE:
            # Unknown symbol: the provider has nothing, as a real one would (exercises "no data").
            self._bars15[symbol] = []
            return []
        anchor, dvol, drift, base_vol = _PROFILE[symbol]
        seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        last_day, cutoff = _last_session_end(self._now)
        days = _trading_days(last_day, _SESSION_DAYS)
        step_vol = dvol / math.sqrt(26)
        # walk forward from an arbitrary start, rescale so the last close lands near the anchor
        price = 100.0
        raw: list[tuple[datetime, float, float, float, float, int]] = []
        regime = 0.0
        for di, d in enumerate(days):
            if di % 23 == 0:
                regime = rng.gauss(drift, dvol * 0.6)
            gap = rng.gauss(0, dvol * 0.35)
            price *= math.exp(gap)
            for k in range(26):
                start = datetime.combine(d, time(9, 30), ET) + timedelta(minutes=15 * k)
                if start >= cutoff:
                    break
                o = price
                ret = rng.gauss(regime / 26, step_vol)
                c = o * math.exp(ret)
                wick = abs(rng.gauss(0, step_vol * 0.7))
                h = max(o, c) * (1 + wick)
                lo = min(o, c) * (1 - abs(rng.gauss(0, step_vol * 0.7)))
                u = 1.0 + 1.6 * ((k - 12.5) / 12.5) ** 2  # U-shaped intraday volume
                v = int(base_vol * u * math.exp(rng.gauss(0, 0.35)))
                raw.append((start, o, h, lo, c, v))
                price = c
        scale = anchor / raw[-1][4] if raw else 1.0
        bars = [
            {
                "start": start,
                "o": round(o * scale, 2),
                "h": round(h * scale, 2),
                "l": round(lo * scale, 2),
                "c": round(c * scale, 2),
                "v": v,
            }
            for start, o, h, lo, c, v in raw
        ]
        self._bars15[symbol] = bars
        self._quotes[symbol] = {"symbol": symbol, "price": bars[-1]["c"], "atr": round(bars[-1]["c"] * dvol, 2)}
        return bars

    @staticmethod
    def _bucket(start: datetime, interval: str) -> datetime:
        if interval in ("15m", "15min"):
            return start
        if interval in ("1h", "60m", "1hour"):
            return start.replace(minute=0)
        if interval in ("4h",):
            return start.replace(hour=9 if start.hour < 13 else 13, minute=0)
        return datetime.combine(start.date(), time(0, 0), ET)

    def ohlcv(self, symbol: str, interval: str = "1d", limit: int = 100) -> list[dict[str, Any]]:
        base = self._generate(symbol.upper())
        out: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for bar in base:
            key = self._bucket(bar["start"], interval)
            if current is None or current["key"] != key:
                if current is not None:
                    out.append(current)
                current = {"key": key, "o": bar["o"], "h": bar["h"], "l": bar["l"], "c": bar["c"], "v": bar["v"]}
            else:
                current["h"] = max(current["h"], bar["h"])
                current["l"] = min(current["l"], bar["l"])
                current["c"] = bar["c"]
                current["v"] += bar["v"]
        if current is not None:
            out.append(current)
        rows = [
            {
                "ts": row["key"].astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "o": row["o"],
                "h": row["h"],
                "l": row["l"],
                "c": row["c"],
                "v": row["v"],
            }
            for row in out
        ]
        return rows[-limit:] if limit else rows

    def quote(self, symbol: str) -> dict[str, Any]:
        self._generate(symbol.upper())
        if symbol.upper() not in self._quotes:
            raise ValueError(f"no market data for {symbol.upper()}")
        return self._quotes[symbol.upper()]


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def seed_scenario(rt: Any, market: ScenarioMarketData) -> None:
    """Populate the dev office through the Runtime and, where no command exists, the DB."""
    from runtime.commands import AddWatchlist, UpsertAnnotation

    db = rt.office.db
    now = datetime.now(UTC)

    def bars(sym: str, tf: str = "1h") -> list[dict[str, Any]]:
        return market.ohlcv(sym, interval=tf, limit=0)

    def t(row: dict[str, Any]) -> int:
        return int(datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).timestamp())

    watch = [
        ("AAPL", "Rottura dei massimi di ottobre con volumi sopra media: in osservazione per ingresso.", "technical_analyst"),
        ("NVDA", "Bozza d'ordine pronta, attende approvazione sull'account manuale.", "portfolio_manager"),
        ("MSFT", "Trimestrale a fine gennaio: seguire guidance su Azure prima di aumentare.", "cockpit"),
        ("AMD", "Momentum in calo dopo il rifiuto a 172; rivedere il supporto.", "market_analyst"),
        ("LLY", "Posizione aperta, trailing attivo.", "portfolio_manager"),
        ("XOM", "Copertura energia se il greggio scende sotto 70.", "cockpit"),
        ("JPM", "Rischio settore finanziario al 24%: niente nuove posizioni sopra il 30%.", "risk_analyst"),
    ]
    for ticker, note, actor in watch:
        rt.execute(AddWatchlist(ticker=ticker, note=note), actor=actor)

    # Chart annotations signed by their authors (TradingView drawing kinds).
    aapl = bars("AAPL")
    hi = max(b["h"] for b in aapl[-140:-20])
    lo = min(b["l"] for b in aapl[-90:])
    swing_a = min(aapl[-120:-60], key=lambda b: b["l"])
    swing_b = min(aapl[-40:], key=lambda b: b["l"])
    annotations = [
        ("ta-aapl-res", "AAPL", "technical_analyst", {"type": "horizontal-line", "points": [{"time": t(aapl[-100]), "price": round(hi, 2)}], "text": "Resistenza ottobre"}),
        ("ta-aapl-sup", "AAPL", "technical_analyst", {"type": "horizontal-line", "points": [{"time": t(aapl[-60]), "price": round(lo, 2)}], "text": "Supporto"}),
        ("ta-aapl-trend", "AAPL", "technical_analyst", {"type": "trend-line", "points": [{"time": t(swing_a), "price": swing_a["l"]}, {"time": t(swing_b), "price": swing_b["l"]}], "text": "Trend rialzista"}),
        ("luca-aapl-1", "AAPL", "cockpit", {"type": "trend-line", "points": [{"time": t(aapl[-70]), "price": aapl[-70]["h"]}, {"time": t(aapl[-12]), "price": aapl[-12]["h"]}], "text": "Canale superiore"}),
        ("risk-aapl-stop", "AAPL", "risk_analyst", {"type": "horizontal-line", "points": [{"time": t(aapl[-30]), "price": round(lo * 0.985, 2)}], "text": "Invalidazione"}),
    ]
    nvda = bars("NVDA")
    n_hi = max(b["h"] for b in nvda[-80:])
    n_lo = min(b["l"] for b in nvda[-50:])
    annotations += [
        ("ta-nvda-res", "NVDA", "technical_analyst", {"type": "horizontal-line", "points": [{"time": t(nvda[-60]), "price": round(n_hi, 2)}], "text": "Massimo recente"}),
        ("ta-nvda-sup", "NVDA", "technical_analyst", {"type": "horizontal-line", "points": [{"time": t(nvda[-40]), "price": round(n_lo, 2)}], "text": "Area di acquisto"}),
        ("luca-nvda-1", "NVDA", "cockpit", {"type": "rectangle", "points": [{"time": t(nvda[-45]), "price": round(n_lo * 1.012, 2)}, {"time": t(nvda[-8]), "price": round(n_lo * 0.992, 2)}], "text": "Zona di accumulo"}),
    ]
    for ann_id, ticker, actor, drawing in annotations:
        rt.execute(UpsertAnnotation(id=ann_id, ticker=ticker, timeframe="1h", drawing=drawing), actor=actor)

    def last(sym: str) -> float:
        return bars(sym)[-1]["c"]

    def draft(sym: str, side: str, entry: float, stop: float, tp: float, qty: int) -> dict[str, Any]:
        risk = abs(entry - stop) * qty
        return {
            "symbol": sym,
            "side": side,
            "entry": f"{entry:.2f}",
            "stop": f"{stop:.2f}",
            "take_profit": f"{tp:.2f}",
            "quantity": str(qty),
            "risk_reward": f"{abs(tp - entry) / abs(entry - stop):.2f}",
            "risk_amount": f"{risk:.2f}",
            "notional": f"{entry * qty:.2f}",
        }

    def order(sym: str, side: str, d: dict[str, Any], approval: str, status: str, ago: timedelta, events: list[tuple[str, dict[str, Any]]]) -> int:
        payload = json.dumps(d, sort_keys=True)
        h = hashlib.sha256(payload.encode()).hexdigest()
        created = now - ago
        oid = db.insert_order(
            ticker=sym, side=side, draft=d, draft_hash=h, approval_status=approval,
            client_order_id=f"ord-{sym.lower()}-{side}-{h[:8]}", status=status,
            broker_order_id=f"alp-{h[8:16]}" if status in ("submitted", "open", "filled") else None,
            created_ts=_iso(created),
        )
        for i, (event, detail) in enumerate(events):
            db.insert_order_event(oid, event, detail, ts=_iso(created + timedelta(minutes=2 * i)))
        return oid

    with db.transaction():
        p = last("NVDA")
        order("NVDA", "buy", draft("NVDA", "buy", round(p * 0.988, 2), round(p * 0.955, 2), round(p * 1.055, 2), 52), "pending", "pending", timedelta(minutes=38), [("created", {"approval_status": "pending"})])
        p = last("AMD")
        order("AMD", "buy", draft("AMD", "buy", round(p * 0.99, 2), round(p * 0.962, 2), round(p * 1.04, 2), 60), "pending", "pending", timedelta(minutes=12), [("created", {"approval_status": "pending"})])
        p = last("MSFT")
        order("MSFT", "buy", draft("MSFT", "buy", round(p * 0.985, 2), round(p * 0.962, 2), round(p * 1.04, 2), 18), "approved", "submitted", timedelta(hours=5), [("created", {"approval_status": "pending"}), ("approved", {"actor": "cockpit"}), ("submitted", {})])
        aapl_entry = round(aapl[-26]["c"], 2)
        aapl_oid = order("AAPL", "buy", draft("AAPL", "buy", aapl_entry, round(aapl_entry * 0.968, 2), round(aapl_entry * 1.06, 2), 40), "auto", "filled", timedelta(days=4), [("created", {"approval_status": "auto"}), ("submitted", {}), ("filled", {"price": aapl_entry, "qty": 40})])
        lly = bars("LLY")
        lly_entry = round(lly[-60]["c"], 2)
        lly_oid = order("LLY", "buy", draft("LLY", "buy", lly_entry, round(lly_entry * 0.955, 2), round(lly_entry * 1.08, 2), 6), "auto", "filled", timedelta(days=9), [("created", {"approval_status": "auto"}), ("submitted", {}), ("filled", {"price": lly_entry, "qty": 6})])
        p = last("JPM")
        order("JPM", "buy", draft("JPM", "buy", round(p * 0.99, 2), round(p * 0.975, 2), round(p * 1.02, 2), 30), "rejected", "rejected", timedelta(days=1, hours=3), [("created", {"approval_status": "pending"}), ("rejected", {"reason": "R:R 1.33 sotto il minimo 1.5", "actor": "cockpit"})])
        p = last("XOM")
        order("XOM", "sell", draft("XOM", "sell", round(p * 1.01, 2), round(p * 1.035, 2), round(p * 0.96, 2), 70), "auto", "cancelled", timedelta(days=2), [("created", {"approval_status": "auto"}), ("cancelled", {"reason": "Bozza scaduta"})])
        tsla = bars("TSLA")
        tsla_entry = round(tsla[-200]["c"], 2)
        tsla_oid = order("TSLA", "buy", draft("TSLA", "buy", tsla_entry, round(tsla_entry * 0.95, 2), round(tsla_entry * 1.1, 2), 20), "auto", "filled", timedelta(days=30), [("filled", {"price": tsla_entry})])
        jpm = bars("JPM")
        jpm_entry = round(jpm[-300]["c"], 2)
        jpm_oid = order("JPM", "buy", draft("JPM", "buy", jpm_entry, round(jpm_entry * 0.97, 2), round(jpm_entry * 1.05, 2), 35), "auto", "filled", timedelta(days=44), [("filled", {"price": jpm_entry})])

        db.insert_trade("AAPL", aapl_oid, aapl_entry, 40, opened_ts=_iso(now - timedelta(days=4)))
        db.insert_trade("LLY", lly_oid, lly_entry, 6, opened_ts=_iso(now - timedelta(days=9)), events=[{"event": "trail_armed", "stop": round(lly_entry * 1.01, 2)}])
        db.insert_trade("TSLA", tsla_oid, tsla_entry, 20, opened_ts=_iso(now - timedelta(days=30)), closed_ts=_iso(now - timedelta(days=24)), exit_reason="sl", exit_price=round(tsla_entry * 0.95, 2))
        db.insert_trade("JPM", jpm_oid, jpm_entry, 35, opened_ts=_iso(now - timedelta(days=44)), closed_ts=_iso(now - timedelta(days=31)), exit_reason="tp", exit_price=round(jpm_entry * 1.05, 2))

        # Portfolio: daily equity history and the latest snapshot with positions.
        aapl_px, lly_px = last("AAPL"), last("LLY")
        positions = [
            {"symbol": "AAPL", "qty": 40, "avg_entry_price": aapl_entry, "current_price": aapl_px, "market_value": round(aapl_px * 40, 2), "unrealized_pl": round((aapl_px - aapl_entry) * 40, 2)},
            {"symbol": "LLY", "qty": 6, "avg_entry_price": lly_entry, "current_price": lly_px, "market_value": round(lly_px * 6, 2), "unrealized_pl": round((lly_px - lly_entry) * 6, 2)},
        ]
        rng = random.Random(7)
        equity = 98_400.0
        for i in range(60, 0, -1):
            day = now - timedelta(days=i)
            if day.weekday() >= 5:
                continue
            equity *= math.exp(rng.gauss(0.0007, 0.004))
            db.insert_portfolio_snapshot(equity=round(equity, 2), cash=round(equity * 0.78, 2), ts=_iso(day.replace(hour=21, minute=0, second=0, microsecond=0)))
        invested = sum(p["market_value"] for p in positions)
        cash = round(equity * 0.97 - invested + 1450.0, 2)
        db.insert_portfolio_snapshot(equity=round(cash + invested, 2), cash=cash, positions=positions, ts=_iso(now - timedelta(minutes=3)))

        # Shared ticker state written by the agents.
        db.set_ticker_state("AAPL", {
            "ticker": "AAPL",
            "analyses": {
                "technical_analyst": "Prezzo sopra EMA20 e SMA50, RSI 61 senza divergenze. Resistenza di ottobre superata con volumi 1,4x la media: il livello diventa supporto. Stop sotto il minimo dell'ultima settimana.",
                "fundamental_analyst": "Margini servizi in crescita, buyback costante. Valutazione piena ma sostenuta dal ciclo iPhone.",
                "risk_analyst": "Esposizione tecnologia al 21% del portafoglio, entro il limite del 30%. Rischio per trade 0,8%.",
                "sentiment_analyst": "Sentiment neutro-positivo; nessuna notizia rilevante nelle ultime 24 ore.",
            },
            "suggestions": {
                "technical_analyst": {"direction": "buy", "conviction": 0.68},
                "fundamental_analyst": {"direction": "hold", "conviction": 0.55},
                "risk_analyst": {"direction": "buy", "conviction": 0.5},
                "sentiment_analyst": {"direction": "hold", "conviction": 0.4},
            },
            "coefficients": {"k_entry": 0.3, "risk_fraction": 0.008, "k_stop": 1.8, "k_tp": 3.2, "k_trail_act": 1.5, "k_trail": 1.2},
            "draft": None,
            "decision": {"action": "hold", "reason": "Posizione aperta in linea con la tesi; nessun incremento prima della conferma sopra il massimo.", "decided_ts": _iso(now - timedelta(hours=6)), "status": "accepted"},
        }, updated_ts=_iso(now - timedelta(hours=6)))
        db.set_ticker_state("NVDA", {
            "ticker": "NVDA",
            "analyses": {
                "technical_analyst": "Ritracciamento ordinato verso l'area di acquisto, volumi in calo sulla discesa. Ingresso limite sotto l'ultimo minimo orario.",
                "market_analyst": "Rotazione verso semiconduttori nelle ultime tre sedute.",
                "risk_analyst": "Rischio 1,0% sul capitale, R:R 2,4. Settore tecnologia salirebbe al 29%.",
            },
            "suggestions": {
                "technical_analyst": {"direction": "buy", "conviction": 0.74},
                "market_analyst": {"direction": "buy", "conviction": 0.62},
                "risk_analyst": {"direction": "buy", "conviction": 0.45},
            },
            "coefficients": {"k_entry": 0.4, "risk_fraction": 0.01, "k_stop": 1.6, "k_tp": 3.8},
            "draft": None,
            "decision": {"action": "buy", "reason": "Convergenza tecnica e di mercato; ordine in attesa di approvazione sull'account manuale.", "decided_ts": _iso(now - timedelta(minutes=40)), "status": "accepted"},
        }, updated_ts=_iso(now - timedelta(minutes=40)))

        # Cycles and the messages the agents exchanged.
        def cycle(sym: str, status: str, opened: timedelta, closed: timedelta | None, outcome: str | None, msgs: list[tuple[str, str]]) -> None:
            cid = db.open_cycle(sym, status="open", opened_ts=_iso(now - opened), budget_used={"messages": len(msgs)})
            if closed is not None:
                db.connection.execute("UPDATE cycles SET status = ?, closed_ts = ?, outcome = ? WHERE id = ?", (status, _iso(now - closed), outcome, cid))
            for i, (agent, text) in enumerate(msgs):
                chat_id = db.get_or_create_chat(agent, sym)
                db.append_message(chat_id, agent, text, cycle_id=cid, ts=_iso(now - opened + timedelta(minutes=3 * i)))

        cycle("AAPL", "closed", timedelta(hours=7), timedelta(hours=6), "hold", [
            ("technical_analyst", "Breakout confermato su base oraria; propongo k_stop 1.8 e k_tp 3.2."),
            ("risk_analyst", "Rischio ok, esposizione settoriale entro i limiti."),
            ("portfolio_manager", "Tengo la posizione, nessun incremento."),
        ])
        cycle("NVDA", "open", timedelta(minutes=46), None, None, [
            ("market_analyst", "Flussi in entrata sui semiconduttori."),
            ("technical_analyst", "Area 172-175 tiene; ingresso limite proposto."),
            ("portfolio_manager", "Bozza accettata, in attesa di approvazione manuale."),
        ])
        cycle("AMD", "open", timedelta(minutes=15), None, None, [
            ("technical_analyst", "Rimbalzo sul supporto, segnale debole."),
        ])

        db.add_inbox("approval", "NVDA: ordine di acquisto in attesa di approvazione (account manuale).", ts=_iso(now - timedelta(minutes=38)))
        db.add_inbox("approval", "AMD: ordine di acquisto in attesa di approvazione (account manuale).", ts=_iso(now - timedelta(minutes=12)))
        db.add_inbox("risk", "JPM: ordine rifiutato dal Risk Gate, R:R 1.33 sotto il minimo 1.5.", ts=_iso(now - timedelta(days=1, hours=3)))
        read_id = db.add_inbox("info", "Riconciliazione broker completata: 2 posizioni, 1 ordine aperto.", ts=_iso(now - timedelta(hours=5)))
        db.mark_inbox_read(read_id)
