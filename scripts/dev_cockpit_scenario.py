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
from decimal import Decimal
from pathlib import Path
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
        self._quotes[symbol] = {
            "symbol": symbol,
            "price": bars[-1]["c"],
            "atr": round(bars[-1]["c"] * dvol, 2),
        }
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
                current = {
                    "key": key,
                    "o": bar["o"],
                    "h": bar["h"],
                    "l": bar["l"],
                    "c": bar["c"],
                    "v": bar["v"],
                }
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


_SECTORS = {
    "AAPL": "Technology",
    "NVDA": "Technology",
    "MSFT": "Technology",
    "AMD": "Technology",
    "GOOGL": "Technology",
    "META": "Technology",
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "JPM": "Financials",
    "XOM": "Energy",
    "LLY": "Health Care",
}
_AGENTS = ("technical_analyst", "market_analyst", "fundamental_analyst", "portfolio_manager")


def _seed_portfolio(
    rt: Any, market: ScenarioMarketData, now: datetime, existing: dict[str, tuple[int, float, int]]
) -> None:
    """Portafoglio per il cockpit: 6 posizioni su 4 settori (Technology vicino al limite),
    storico di trade chiusi con motivi e agenti diversi, equity di oltre un anno, SPY giornaliero,
    una modifica ai limiti e un broker finto che esegue close_position/modify_exit.
    Solo sviluppo, mai produzione."""
    from execution.risk_limits import RiskLimitsStore, defaults_from_settings
    from tests.fakes.bracket_broker import FakeBrokerOrder

    db = rt.office.db
    broker = rt.office.order_flow.broker

    def last(sym: str) -> float:
        return market.ohlcv(sym, interval="1h", limit=0)[-1]["c"]

    for sym, sector in _SECTORS.items():
        db.connection.execute(
            "INSERT OR REPLACE INTO securities(symbol, name, sector) VALUES (?, ?, ?)",
            (sym, sym, sector),
        )

    def filled_order(
        sym: str, entry: float, stop: float, tp: float, qty: int, ago: timedelta, tag: str
    ) -> int:
        d = {
            "symbol": sym,
            "side": "buy",
            "entry": f"{entry:.2f}",
            "stop": f"{stop:.2f}",
            "take_profit": f"{tp:.2f}",
            "quantity": str(qty),
            "notional": f"{entry * qty:.2f}",
        }
        h = hashlib.sha256(f"{tag}-{sym}-{entry}-{qty}".encode()).hexdigest()
        oid = db.insert_order(
            ticker=sym,
            side="buy",
            draft=d,
            draft_hash=h,
            approval_status="auto",
            client_order_id=f"{tag}-{sym.lower()}-{h[:8]}",
            status="filled",
            broker_order_id=f"alp-{h[8:16]}",
            created_ts=_iso(now - ago),
        )
        db.insert_order_event(oid, "filled", {"price": entry, "qty": qty}, ts=_iso(now - ago))
        return oid

    # posizioni aperte: AAPL e LLY esistono già; si aggiungono GOOGL, META, JPM, XOM
    opens: dict[str, tuple[int, float, int]] = dict(existing)
    extra = {
        "GOOGL": (32, 6, "market_analyst", 0.965, 1.07),
        "META": (14, 12, "portfolio_manager", 0.96, 1.08),
        "JPM": (35, 17, "fundamental_analyst", 0.97, 1.05),
        "XOM": (60, 3, "market_analyst", 0.962, 1.045),
    }
    for sym, (qty, days, who, sp, tp) in extra.items():
        price = last(sym)
        entry = round(price * (0.985 if sym != "XOM" else 1.012), 2)
        stop = round(min(entry * sp, price * 0.965), 2)
        target = round(max(entry * tp, price * 1.05), 2)
        oid = filled_order(sym, entry, stop, target, qty, timedelta(days=days), "port")
        db.insert_trade(
            sym,
            oid,
            entry,
            qty,
            opened_ts=_iso(now - timedelta(days=days)),
            stop_price=stop,
            target_price=target,
            initial_stop=round(entry * sp, 2),
            proposed_by=who,
        )
        opens[sym] = (oid, entry, qty)

    positions = []
    for sym, (_oid, entry, qty) in opens.items():
        px = last(sym)
        positions.append(
            {
                "symbol": sym,
                "qty": qty,
                "avg_entry_price": entry,
                "current_price": px,
                "market_value": round(px * qty, 2),
                "unrealized_pl": round((px - entry) * qty, 2),
            }
        )
        broker.market_prices[sym] = Decimal(str(px))
        order = db.get_order(opens[sym][0])
        bid = order["broker_order_id"]
        trade = db.connection.execute(
            "SELECT stop_price, target_price FROM trades WHERE entry_order_id = ?", (opens[sym][0],)
        ).fetchone()
        broker.orders[bid] = FakeBrokerOrder(
            broker_order_id=bid,
            client_order_id=order["client_order_id"],
            symbol=sym,
            side="buy",
            quantity=Decimal(qty),
            limit_price=Decimal(str(entry)),
            take_profit=Decimal(str(trade["target_price"])),
            stop_loss=Decimal(str(trade["stop_price"])),
            status="filled",
            filled_quantity=Decimal(qty),
            average_fill_price=Decimal(str(entry)),
        )
        broker.client_map[order["client_order_id"]] = bid

    # trade chiusi: ~24 in un anno, motivi e agenti diversi, alcuni negli ultimi giorni
    rng = random.Random(11)
    for i in range(24):
        sym = rng.choice(sorted(_PROFILE))
        anchor = _PROFILE[sym][0]
        entry = round(anchor * rng.uniform(0.8, 1.05), 2)
        reason = rng.choices(["tp", "sl", "pm_sell", "expired"], weights=[40, 35, 20, 5])[0]
        pct = {
            "tp": rng.uniform(0.03, 0.09),
            "sl": -rng.uniform(0.02, 0.045),
            "pm_sell": rng.uniform(-0.03, 0.05),
            "expired": rng.uniform(-0.01, 0.015),
        }[reason]
        qty = max(1, int(rng.uniform(3000, 9000) / entry))
        initial_stop = round(entry * (1 - rng.uniform(0.03, 0.05)), 2)
        closed_ago = timedelta(days=rng.uniform(0.2, 6.0) if i < 5 else rng.uniform(7, 355))
        held = timedelta(days=rng.randint(2, 21), hours=rng.randint(0, 5))
        oid = filled_order(
            sym, entry, initial_stop, round(entry * 1.07, 2), qty, closed_ago + held, f"hist{i}"
        )
        exit_px = round(entry * (1 + pct), 2)
        who = None if i == 7 else rng.choice(_AGENTS)
        tid = db.insert_trade(
            sym,
            oid,
            entry,
            qty,
            opened_ts=_iso(now - closed_ago - held),
            closed_ts=_iso(now - closed_ago),
            exit_reason=reason,
            exit_price=exit_px,
            initial_stop=initial_stop,
            proposed_by=who,
        )
        db.connection.execute(
            "UPDATE trades SET realized_pnl = ?, closed_qty = ? WHERE id = ?",
            (round((exit_px - entry) * qty, 2), qty, tid),
        )

    # equity giornaliera (>1 anno) correlata a SPY, che termina sul valore delle posizioni + cassa
    invested = sum(p["market_value"] for p in positions)
    cash = round(invested * 1.1, 2)
    equity_end = round(cash + invested, 2)
    days = [d for d in (now - timedelta(days=i) for i in range(400, 0, -1)) if d.weekday() < 5]
    market_ret = [rng.gauss(0.0004, 0.009) for _ in days]
    eq_path, spy_path, e, b = [], [], 1.0, 1.0
    for m in market_ret:
        e *= math.exp(0.7 * m + rng.gauss(0.0003, 0.004))
        b *= math.exp(m)
        eq_path.append(e)
        spy_path.append(b)
    scale = equity_end / eq_path[-1] / 1.0037  # l'ultimo snapshot è +0,37% sul giorno precedente
    for d, e, b in zip(days, eq_path, spy_path, strict=True):
        db.insert_portfolio_snapshot(
            equity=round(e * scale, 2),
            cash=round(e * scale * 0.55, 2),
            ts=_iso(d.replace(hour=21, minute=0, second=0, microsecond=0)),
        )
        px = round(430 * b, 2)
        db.connection.execute(
            "INSERT OR REPLACE INTO prices_ohlcv(symbol, ts, interval, o, h, l, c, v, source, fetched_at) VALUES ('SPY', ?, '1d', ?, ?, ?, ?, 1, 'scenario', ?)",
            (d.strftime("%Y-%m-%dT00:00:00Z"), px, px, px, px, _iso(now)),
        )
    db.insert_portfolio_snapshot(
        equity=equity_end, cash=cash, positions=positions, ts=_iso(now - timedelta(minutes=3))
    )

    # una modifica ai limiti nella cronologia
    store = RiskLimitsStore(db, defaults_from_settings(rt.office.settings.limits))
    store.update(
        {"max_sector_fraction": 0.32},
        "Tecnologia in trend: concedo più spazio al settore",
        "cockpit",
    )


def seed_scenario(rt: Any, market: ScenarioMarketData) -> None:
    """Populate the dev office through the Runtime and, where no command exists, the DB."""
    from runtime.commands import AddWatchlist, UpsertAnnotation

    db = rt.office.db
    now = datetime.now(UTC)

    # Seed 4-5 news sources
    s1 = db.add_news_source("alpaca", "Alpaca News", "https://data.alpaca.markets/v1/news")
    s2 = db.add_news_source("rss", "TechCrunch RSS", "https://techcrunch.com/feed/")
    s3 = db.add_news_source("rss", "Macro RSS", "https://macro.example.com/rss")
    db.update_news_source_status(s3, "error", "Connection timeout")
    s4 = db.add_news_source("openbb", "OpenBB Terminal", None)
    db.update_news_source_status(s4, "unavailable", "OpenBB not installed")

    # Seed 75 news items across providers and tickers
    tickers_pool = ["AAPL", "NVDA", "MSFT", "AMD", "LLY", "XOM", "JPM", "TSLA", "GOOGL", "META", "AMZN"]
    themes_pool = ["technology", "macro", "earnings", "semiconductors", "energy"]
    news_ids = []
    for i in range(1, 76):
        sym = tickers_pool[i % len(tickers_pool)]
        theme = themes_pool[i % len(themes_pool)]
        pub = now - timedelta(hours=i * 2)
        nid = db.insert_news(
            headline=f"Market briefing {i} for {sym}: sector outlook and catalysts",
            summary=f"Summary for news item {i} regarding {sym}.",
            full_text=f"Detailed full text analysis for news {i} covering {sym}.",
            url=f"https://example.com/news/{i}",
            source_id=s1 if i % 2 == 0 else s2,
            source="Alpaca News" if i % 2 == 0 else "TechCrunch RSS",
            provider="alpaca" if i % 2 == 0 else "rss",
            published_ts=pub.isoformat().replace("+00:00", "Z"),
            tickers=[sym],
            themes=[theme],
        )
        news_ids.append(nid)

    # Seed usage traces (read, cited, forwarded)
    for idx, nid in enumerate(news_ids[:35]):
        db.log_news_usage(news_id=nid, agent="sentiment_analyst", kind="read", cycle_id=1, chat_id=1)
        if idx % 2 == 0:
            db.log_news_usage(news_id=nid, agent="portfolio_manager", kind="cited", note=f"Cited in dossier {idx}")
        if idx % 5 == 0:
            db.log_news_usage(news_id=nid, agent="portfolio_manager", kind="forwarded", chat_id=1, note="Nota di Luca")

    # Seed calendar week (macro & earnings)
    for day_offset in range(-3, 5):
        evt_dt = now + timedelta(days=day_offset)
        db.insert_calendar_event(
            kind="macro",
            ts=evt_dt.replace(hour=14, minute=30, second=0, microsecond=0).isoformat().replace("+00:00", "Z"),
            title=f"US Macro Economic Report (Day {day_offset})",
            country="US",
            importance="high" if day_offset == 0 else "medium",
            actual=3.2 if day_offset < 0 else None,
            forecast=3.1,
            previous=3.0,
            source="openbb",
        )
        sym = tickers_pool[day_offset % len(tickers_pool)]
        db.insert_calendar_event(
            kind="earnings",
            ts=evt_dt.replace(hour=20, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z"),
            title=f"Earnings Call: {sym}",
            ticker=sym,
            importance="high",
            forecast=1.45,
            actual=1.52 if day_offset < 0 else None,
            source="openbb",
        )


    def bars(sym: str, tf: str = "1h") -> list[dict[str, Any]]:
        return market.ohlcv(sym, interval=tf, limit=0)

    def t(row: dict[str, Any]) -> int:
        return int(datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).timestamp())

    watch = [
        (
            "AAPL",
            "Rottura dei massimi di ottobre con volumi sopra media: in osservazione per ingresso.",
            "technical_analyst",
        ),
        (
            "NVDA",
            "Bozza d'ordine pronta, attende approvazione sull'account manuale.",
            "portfolio_manager",
        ),
        (
            "MSFT",
            "Trimestrale a fine gennaio: seguire guidance su Azure prima di aumentare.",
            "cockpit",
        ),
        ("AMD", "Momentum in calo dopo il rifiuto a 172; rivedere il supporto.", "market_analyst"),
        ("LLY", "Posizione aperta, trailing attivo.", "portfolio_manager"),
        ("XOM", "Copertura energia se il greggio scende sotto 70.", "cockpit"),
        (
            "JPM",
            "Rischio settore finanziario al 24%: niente nuove posizioni sopra il 30%.",
            "risk_analyst",
        ),
    ]
    for ticker, note, actor in watch:
        rt.execute(AddWatchlist(ticker=ticker, note=note), actor=actor)

    from agents.backend import ToolCall
    from runtime.commands import AddDossierNote

    env = rt.office.get_env(None)
    for index, (ticker, _, _) in enumerate(watch[:5]):
        agent = f"ticker:{ticker}"
        db.register_agent(agent, "ticker_agent")
        db.set_agent_status(
            agent,
            ("working", "waiting", "idle", "idle", "working")[index],
            {"ticker": ticker} if index in (0, 1, 4) else None,
        )
        tools = {tool.name: tool for tool in env.tools_for(agent)}
        for analyst in ("technical_analyst", "fundamental_analyst"):
            write = next(tool for tool in env.tools_for(analyst) if tool.name == "write_analysis")
            write.execute(
                ToolCall(
                    id=f"dev-{ticker}-{analyst}",
                    name="write_analysis",
                    args={
                        "ticker": ticker,
                        "section_text": f"Scenario demo {analyst} per {ticker}.",
                    },
                )
            )
        tools["write_thesis"].execute(
            ToolCall(
                id=f"thesis-{ticker}",
                name="write_thesis",
                args={
                    "ticker": ticker,
                    "direction": "buy",
                    "conviction": 0.7,
                    "pro": ["Trend favorevole"],
                    "contro": ["Volatilità"],
                    "time_horizon": "3 mesi",
                },
            )
        )
        if index in (1, 2, 3):
            proposal = tools["submit_proposal"].execute(
                ToolCall(
                    id=f"proposal-{ticker}",
                    name="submit_proposal",
                    args={
                        "ticker": ticker,
                        "direction": "buy",
                        "conviction": 0.7,
                        "reason": "Scenario demo",
                    },
                )
            )
            if index == 2:
                env.decide_proposal(
                    proposal["id"],
                    "defer",
                    "Rivedere",
                    (now + timedelta(days=3)).isoformat(),
                    "portfolio_manager",
                )
            elif index == 3:
                env.decide_proposal(
                    proposal["id"], "accept", "Scenario demo", None, "portfolio_manager"
                )
        if index == 0:
            rt.execute(
                AddDossierNote(ticker=ticker, text="Verificare il margine operativo"),
                actor="user",
                command_id="dev-note",
            )
            tools["write_lesson"].execute(
                ToolCall(
                    id="lesson-aapl",
                    name="write_lesson",
                    args={
                        "ticker": ticker,
                        "text": "Attendere conferma dei volumi.",
                        "exit_reason": "stop_loss",
                    },
                )
            )
            db.write_dossier_section(
                ticker,
                "desks",
                {
                    "agent": "sentiment_analyst",
                    "section": "sentiment_analyst",
                    "text": "Analisi storica",
                    "ts": "2020-01-01T00:00:00Z",
                    "reference_date": "2020-01-01",
                    "confidence": None,
                    "status": "stale",
                },
                "sentiment_analyst",
                now.isoformat(),
            )

    # Chart annotations signed by their authors (TradingView drawing kinds).
    aapl = bars("AAPL")
    hi = max(b["h"] for b in aapl[-140:-20])
    lo = min(b["l"] for b in aapl[-90:])
    swing_a = min(aapl[-120:-60], key=lambda b: b["l"])
    swing_b = min(aapl[-40:], key=lambda b: b["l"])
    annotations = [
        (
            "ta-aapl-res",
            "AAPL",
            "technical_analyst",
            {
                "type": "horizontal-line",
                "points": [{"time": t(aapl[-100]), "price": round(hi, 2)}],
                "text": "Resistenza ottobre",
            },
        ),
        (
            "ta-aapl-sup",
            "AAPL",
            "technical_analyst",
            {
                "type": "horizontal-line",
                "points": [{"time": t(aapl[-60]), "price": round(lo, 2)}],
                "text": "Supporto",
            },
        ),
        (
            "ta-aapl-trend",
            "AAPL",
            "technical_analyst",
            {
                "type": "trend-line",
                "points": [
                    {"time": t(swing_a), "price": swing_a["l"]},
                    {"time": t(swing_b), "price": swing_b["l"]},
                ],
                "text": "Trend rialzista",
            },
        ),
        (
            "luca-aapl-1",
            "AAPL",
            "cockpit",
            {
                "type": "trend-line",
                "points": [
                    {"time": t(aapl[-70]), "price": aapl[-70]["h"]},
                    {"time": t(aapl[-12]), "price": aapl[-12]["h"]},
                ],
                "text": "Canale superiore",
            },
        ),
        (
            "risk-aapl-stop",
            "AAPL",
            "risk_analyst",
            {
                "type": "horizontal-line",
                "points": [{"time": t(aapl[-30]), "price": round(lo * 0.985, 2)}],
                "text": "Invalidazione",
            },
        ),
    ]
    nvda = bars("NVDA")
    n_hi = max(b["h"] for b in nvda[-80:])
    n_lo = min(b["l"] for b in nvda[-50:])
    annotations += [
        (
            "ta-nvda-res",
            "NVDA",
            "technical_analyst",
            {
                "type": "horizontal-line",
                "points": [{"time": t(nvda[-60]), "price": round(n_hi, 2)}],
                "text": "Massimo recente",
            },
        ),
        (
            "ta-nvda-sup",
            "NVDA",
            "technical_analyst",
            {
                "type": "horizontal-line",
                "points": [{"time": t(nvda[-40]), "price": round(n_lo, 2)}],
                "text": "Area di acquisto",
            },
        ),
        (
            "luca-nvda-1",
            "NVDA",
            "cockpit",
            {
                "type": "rectangle",
                "points": [
                    {"time": t(nvda[-45]), "price": round(n_lo * 1.012, 2)},
                    {"time": t(nvda[-8]), "price": round(n_lo * 0.992, 2)},
                ],
                "text": "Zona di accumulo",
            },
        ),
    ]
    for ann_id, ticker, actor, drawing in annotations:
        rt.execute(
            UpsertAnnotation(id=ann_id, ticker=ticker, timeframe="1h", drawing=drawing), actor=actor
        )

    def last(sym: str) -> float:
        return bars(sym)[-1]["c"]

    def draft(
        sym: str, side: str, entry: float, stop: float, tp: float, qty: int
    ) -> dict[str, Any]:
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

    def order(
        sym: str,
        side: str,
        d: dict[str, Any],
        approval: str,
        status: str,
        ago: timedelta,
        events: list[tuple[str, dict[str, Any]]],
    ) -> int:
        payload = json.dumps(d, sort_keys=True)
        h = hashlib.sha256(payload.encode()).hexdigest()
        created = now - ago
        oid = db.insert_order(
            ticker=sym,
            side=side,
            draft=d,
            draft_hash=h,
            approval_status=approval,
            client_order_id=f"ord-{sym.lower()}-{side}-{h[:8]}",
            status=status,
            broker_order_id=f"alp-{h[8:16]}" if status in ("submitted", "open", "filled") else None,
            created_ts=_iso(created),
        )
        for i, (event, detail) in enumerate(events):
            db.insert_order_event(oid, event, detail, ts=_iso(created + timedelta(minutes=2 * i)))
        return oid

    with db.transaction():
        p = last("NVDA")
        order(
            "NVDA",
            "buy",
            draft("NVDA", "buy", round(p * 0.988, 2), round(p * 0.955, 2), round(p * 1.055, 2), 52),
            "pending",
            "pending",
            timedelta(minutes=38),
            [("created", {"approval_status": "pending"})],
        )
        p = last("AMD")
        order(
            "AMD",
            "buy",
            draft("AMD", "buy", round(p * 0.99, 2), round(p * 0.962, 2), round(p * 1.04, 2), 60),
            "pending",
            "pending",
            timedelta(minutes=12),
            [("created", {"approval_status": "pending"})],
        )
        p = last("MSFT")
        order(
            "MSFT",
            "buy",
            draft("MSFT", "buy", round(p * 0.985, 2), round(p * 0.962, 2), round(p * 1.04, 2), 18),
            "approved",
            "submitted",
            timedelta(hours=5),
            [
                ("created", {"approval_status": "pending"}),
                ("approved", {"actor": "cockpit"}),
                ("submitted", {}),
            ],
        )
        aapl_entry = round(aapl[-26]["c"], 2)
        aapl_oid = order(
            "AAPL",
            "buy",
            draft(
                "AAPL",
                "buy",
                aapl_entry,
                round(aapl_entry * 0.968, 2),
                round(aapl_entry * 1.06, 2),
                40,
            ),
            "auto",
            "filled",
            timedelta(days=4),
            [
                ("created", {"approval_status": "auto"}),
                ("submitted", {}),
                ("filled", {"price": aapl_entry, "qty": 40}),
            ],
        )
        lly = bars("LLY")
        lly_entry = round(lly[-60]["c"], 2)
        lly_oid = order(
            "LLY",
            "buy",
            draft(
                "LLY", "buy", lly_entry, round(lly_entry * 0.955, 2), round(lly_entry * 1.08, 2), 6
            ),
            "auto",
            "filled",
            timedelta(days=9),
            [
                ("created", {"approval_status": "auto"}),
                ("submitted", {}),
                ("filled", {"price": lly_entry, "qty": 6}),
            ],
        )
        p = last("JPM")
        order(
            "JPM",
            "buy",
            draft("JPM", "buy", round(p * 0.99, 2), round(p * 0.975, 2), round(p * 1.02, 2), 30),
            "rejected",
            "rejected",
            timedelta(days=1, hours=3),
            [
                ("created", {"approval_status": "pending"}),
                ("rejected", {"reason": "R:R 1.33 sotto il minimo 1.5", "actor": "cockpit"}),
            ],
        )
        p = last("XOM")
        order(
            "XOM",
            "sell",
            draft("XOM", "sell", round(p * 1.01, 2), round(p * 1.035, 2), round(p * 0.96, 2), 70),
            "auto",
            "cancelled",
            timedelta(days=2),
            [("created", {"approval_status": "auto"}), ("cancelled", {"reason": "Bozza scaduta"})],
        )
        tsla = bars("TSLA")
        tsla_entry = round(tsla[-200]["c"], 2)
        tsla_oid = order(
            "TSLA",
            "buy",
            draft(
                "TSLA",
                "buy",
                tsla_entry,
                round(tsla_entry * 0.95, 2),
                round(tsla_entry * 1.1, 2),
                20,
            ),
            "auto",
            "filled",
            timedelta(days=30),
            [("filled", {"price": tsla_entry})],
        )
        jpm = bars("JPM")
        jpm_entry = round(jpm[-300]["c"], 2)
        jpm_oid = order(
            "JPM",
            "buy",
            draft(
                "JPM", "buy", jpm_entry, round(jpm_entry * 0.97, 2), round(jpm_entry * 1.05, 2), 35
            ),
            "auto",
            "filled",
            timedelta(days=44),
            [("filled", {"price": jpm_entry})],
        )

        aapl_now, lly_now = last("AAPL"), last("LLY")
        db.insert_trade(
            "AAPL",
            aapl_oid,
            aapl_entry,
            40,
            opened_ts=_iso(now - timedelta(days=4)),
            stop_price=min(round(aapl_entry * 0.968, 2), round(aapl_now * 0.97, 2)),
            target_price=round(aapl_entry * 1.06, 2)
            if aapl_entry * 1.06 > aapl_now
            else round(aapl_now * 1.04, 2),
            initial_stop=round(aapl_entry * 0.968, 2),
            proposed_by="technical_analyst",
        )
        db.insert_trade(
            "LLY",
            lly_oid,
            lly_entry,
            6,
            opened_ts=_iso(now - timedelta(days=9)),
            events=[{"event": "trail_armed", "stop": round(lly_entry * 1.01, 2)}],
            stop_price=min(round(lly_entry * 1.01, 2), round(lly_now * 0.97, 2)),
            target_price=max(round(lly_entry * 1.08, 2), round(lly_now * 1.05, 2)),
            initial_stop=round(lly_entry * 0.955, 2),
            proposed_by="portfolio_manager",
        )
        db.insert_trade(
            "TSLA",
            tsla_oid,
            tsla_entry,
            20,
            opened_ts=_iso(now - timedelta(days=30)),
            closed_ts=_iso(now - timedelta(days=24)),
            exit_reason="sl",
            exit_price=round(tsla_entry * 0.95, 2),
            initial_stop=round(tsla_entry * 0.95, 2),
            proposed_by="technical_analyst",
        )
        db.insert_trade(
            "JPM",
            jpm_oid,
            jpm_entry,
            35,
            opened_ts=_iso(now - timedelta(days=44)),
            closed_ts=_iso(now - timedelta(days=31)),
            exit_reason="tp",
            exit_price=round(jpm_entry * 1.05, 2),
            initial_stop=round(jpm_entry * 0.97, 2),
            proposed_by="fundamental_analyst",
        )

        _seed_portfolio(
            rt, market, now, {"AAPL": (aapl_oid, aapl_entry, 40), "LLY": (lly_oid, lly_entry, 6)}
        )

        # Shared ticker state written by the agents.
        db.set_ticker_state(
            "AAPL",
            {
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
                "coefficients": {
                    "k_entry": 0.3,
                    "risk_fraction": 0.008,
                    "k_stop": 1.8,
                    "k_tp": 3.2,
                    "k_trail_act": 1.5,
                    "k_trail": 1.2,
                },
                "draft": None,
                "decision": {
                    "action": "hold",
                    "reason": "Posizione aperta in linea con la tesi; nessun incremento prima della conferma sopra il massimo.",
                    "decided_ts": _iso(now - timedelta(hours=6)),
                    "status": "accepted",
                },
            },
            updated_ts=_iso(now - timedelta(hours=6)),
        )
        db.set_ticker_state(
            "NVDA",
            {
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
                "decision": {
                    "action": "buy",
                    "reason": "Convergenza tecnica e di mercato; ordine in attesa di approvazione sull'account manuale.",
                    "decided_ts": _iso(now - timedelta(minutes=40)),
                    "status": "accepted",
                },
            },
            updated_ts=_iso(now - timedelta(minutes=40)),
        )

        # Cycles and the messages the agents exchanged.
        def cycle(
            sym: str,
            status: str,
            opened: timedelta,
            closed: timedelta | None,
            outcome: str | None,
            msgs: list[tuple[str, str]],
        ) -> None:
            cid = db.open_cycle(
                sym,
                status="open",
                opened_ts=_iso(now - opened),
                budget_used={"messages": len(msgs)},
            )
            if closed is not None:
                db.connection.execute(
                    "UPDATE cycles SET status = ?, closed_ts = ?, outcome = ? WHERE id = ?",
                    (status, _iso(now - closed), outcome, cid),
                )
            for i, (agent, text) in enumerate(msgs):
                chat_id = db.get_or_create_chat(agent, sym)
                db.append_message(
                    chat_id,
                    agent,
                    text,
                    cycle_id=cid,
                    ts=_iso(now - opened + timedelta(minutes=3 * i)),
                )

        cycle(
            "AAPL",
            "closed",
            timedelta(hours=7),
            timedelta(hours=6),
            "hold",
            [
                (
                    "technical_analyst",
                    "Breakout confermato su base oraria; propongo k_stop 1.8 e k_tp 3.2.",
                ),
                ("risk_analyst", "Rischio ok, esposizione settoriale entro i limiti."),
                ("portfolio_manager", "Tengo la posizione, nessun incremento."),
            ],
        )
        cycle(
            "NVDA",
            "open",
            timedelta(minutes=46),
            None,
            None,
            [
                ("market_analyst", "Flussi in entrata sui semiconduttori."),
                ("technical_analyst", "Area 172-175 tiene; ingresso limite proposto."),
                ("portfolio_manager", "Bozza accettata, in attesa di approvazione manuale."),
            ],
        )
        cycle(
            "AMD",
            "open",
            timedelta(minutes=15),
            None,
            None,
            [
                ("technical_analyst", "Rimbalzo sul supporto, segnale debole."),
            ],
        )

        db.add_inbox(
            "approval",
            "NVDA: ordine di acquisto in attesa di approvazione (account manuale).",
            ts=_iso(now - timedelta(minutes=38)),
        )
        db.add_inbox(
            "approval",
            "AMD: ordine di acquisto in attesa di approvazione (account manuale).",
            ts=_iso(now - timedelta(minutes=12)),
        )
        db.add_inbox(
            "risk",
            "JPM: ordine rifiutato dal Risk Gate, R:R 1.33 sotto il minimo 1.5.",
            ts=_iso(now - timedelta(days=1, hours=3)),
        )
        read_id = db.add_inbox(
            "info",
            "Riconciliazione broker completata: 2 posizioni, 1 ordine aperto.",
            ts=_iso(now - timedelta(hours=5)),
        )
        db.mark_inbox_read(read_id)

        # Stati degli agenti per l'Ufficio (working, waiting, idle)
        db.set_agent_status(
            "portfolio_manager",
            "working",
            {
                "type": "cycle",
                "ticker": "NVDA",
                "cycle_id": 2,
                "description": "Valutazione ordine NVDA",
            },
            ts=_iso(now - timedelta(minutes=40)),
        )
        db.set_agent_status(
            "technical_analyst",
            "working",
            {
                "type": "cycle",
                "ticker": "AMD",
                "cycle_id": 3,
                "description": "Analisi supporto orario",
            },
            ts=_iso(now - timedelta(minutes=15)),
        )
        db.set_agent_status(
            "market_analyst",
            "waiting",
            {"type": "task", "ticker": "SEMICONDUCTORS", "description": "Attesa apertura sessione"},
            ts=_iso(now - timedelta(hours=1)),
        )
        db.set_agent_status(
            "risk_analyst",
            "waiting",
            {
                "type": "task",
                "ticker": "PORTFOLIO",
                "description": "Verifica esposizione settoriale",
            },
            ts=_iso(now - timedelta(hours=2)),
        )
        db.set_agent_status("sentiment_analyst", "idle", None, ts=_iso(now - timedelta(hours=4)))
        db.set_agent_status("fundamental_analyst", "idle", None, ts=_iso(now - timedelta(hours=5)))
        db.set_agent_status("subagent", "idle", None, ts=_iso(now - timedelta(days=1)))

        # Chat aggiuntive con messaggi di Luca e degli agenti
        pm_luca_chat = db.get_or_create_chat("portfolio_manager", "direct")
        db.append_message(
            pm_luca_chat,
            "Luca",
            "Ciao PM, oggi privilegiamo semiconduttori con R:R sopra 2.",
            ts=_iso(now - timedelta(hours=2)),
        )
        db.append_message(
            pm_luca_chat,
            "portfolio_manager",
            "Ricevuto Luca. NVDA ha R:R 2.4 stimato, ho preparato la bozza.",
            ts=_iso(now - timedelta(hours=1, minutes=55)),
        )

        ma_macro_chat = db.get_or_create_chat("market_analyst", "macro")
        db.append_message(
            ma_macro_chat,
            "market_analyst",
            "Dati CPI in linea con il consensus (+0.2% MoM). Rendimenti Treasury decennale stabili al 4.38%.",
            ts=_iso(now - timedelta(hours=3)),
        )
        db.append_message(
            ma_macro_chat,
            "Luca",
            "Occhio alla conferenza stampa Fed delle 14:00.",
            ts=_iso(now - timedelta(hours=2, minutes=30)),
        )
        db.append_message(
            ma_macro_chat,
            "market_analyst",
            "Segnato. Nessun nuovo trade aperto durante la conferenza.",
            ts=_iso(now - timedelta(hours=2, minutes=25)),
        )

        ma_semi_chat = db.get_or_create_chat("market_analyst", "semiconductors")
        db.append_message(
            ma_semi_chat,
            "market_analyst",
            "Flussi istituzionali su ETF SOXX e SMH in aumento del 18% rispetto alla media a 20 giorni.",
            ts=_iso(now - timedelta(hours=4)),
        )

        ta_tsla_chat = db.get_or_create_chat("technical_analyst", "TSLA")
        db.append_message(
            ta_tsla_chat,
            "technical_analyst",
            "TSLA tocca resistenza dinamica a 245. Possibile ritracciamento.",
            ts=_iso(now - timedelta(days=1, hours=2)),
        )

        # Chiamate ai tool: riuscite, fallite e compattate
        db.log_tool_call(
            agent="technical_analyst",
            tool="indicators",
            params={"ticker": "NVDA", "timeframe": "1h", "names": "ema20,rsi14,atr14"},
            result={"ema20": 174.2, "rsi14": 61.5, "atr14": 4.12},
            duration_ms=85,
            cycle_id=2,
            chat_id=db.get_or_create_chat("technical_analyst", "NVDA"),
            ts=_iso(now - timedelta(minutes=42)),
        )
        db.log_tool_call(
            agent="technical_analyst",
            tool="read_bars",
            params={"ticker": "AMD", "limit": 50, "timeframe": "1h"},
            result={"bars_count": 50, "latest_close": 118.45},
            duration_ms=120,
            cycle_id=3,
            chat_id=db.get_or_create_chat("technical_analyst", "AMD"),
            ts=_iso(now - timedelta(minutes=14)),
        )
        db.log_tool_call(
            agent="market_analyst",
            tool="macro_series",
            params={"series_id": "CPIAUCSL"},
            result={"value": 314.5, "change_pct": 0.2},
            duration_ms=95,
            chat_id=ma_macro_chat,
            ts=_iso(now - timedelta(hours=3, minutes=1)),
        )
        # Notizie, fonti, traccia d'uso e calendario
        _s1 = db.add_news_source("alpaca", "Alpaca News", "https://api.alpaca.markets/news")
        s2 = db.add_news_source("rss", "Reuters Tech", "https://feeds.reuters.com/reuters/technologyNews")
        s3 = db.add_news_source("rss", "Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss")
        s4 = db.add_news_source("rss", "Broken Feed", "https://example.com/broken-feed.xml")
        db.update_news_source_status(s4, "error", "Timeout connecting to RSS feed")
        s5 = db.add_news_source("openbb", "OpenBB Provider", None)
        db.update_news_source_status(s5, "unavailable", "OpenBB API key not configured")

        tickers_list = ["AAPL", "NVDA", "MSFT", "AMD", "LLY", "TSLA", "GOOGL", "META", "AMZN"]
        themes_list = ["technology", "semiconductors", "macro", "earnings"]
        news_ids = []
        for i in range(75):
            sym = tickers_list[i % len(tickers_list)]
            theme = themes_list[i % len(themes_list)]
            pub = now - timedelta(hours=i * 2)
            nid = db.insert_news(
                headline=f"News update {i+1}: {sym} shows strong momentum in {theme}",
                summary=f"Market analysis and updates regarding {sym} and sector trends.",
                full_text=f"Full article text for news item {i+1} covering {sym} in depth...",
                url=f"https://example.com/news-{i+1}",
                source_id=s2 if i % 2 == 0 else s3,
                source="Reuters Tech" if i % 2 == 0 else "Bloomberg Markets",
                provider="rss",
                published_ts=_iso(pub),
                tickers=[sym],
                themes=[theme],
                has_full_text=1,
            )
            news_ids.append(nid)

        for idx, nid in enumerate(news_ids[:40]):
            db.log_news_usage(news_id=nid, agent="sentiment_analyst", kind="read", cycle_id=1, topic=tickers_list[idx % len(tickers_list)], ts=_iso(now - timedelta(hours=idx)))
        for idx, nid in enumerate(news_ids[:15]):
            db.log_news_usage(news_id=nid, agent="portfolio_manager", kind="cited", cycle_id=1, topic=tickers_list[idx % len(tickers_list)], ts=_iso(now - timedelta(hours=idx)))
        db.log_news_usage(news_id=news_ids[0], agent="portfolio_manager", kind="forwarded", note="Da guardare con attenzione", ts=_iso(now - timedelta(hours=1)))

        cal_items = [
            ("macro", now - timedelta(days=2), "US Non-Farm Payrolls", "US", None, "high", 225.0, 200.0, 180.0, "openbb"),
            ("macro", now - timedelta(days=1), "ECB Rate Decision", "EU", None, "high", 3.25, 3.25, 3.5, "openbb"),
            ("macro", now + timedelta(days=1), "US CPI Inflation MoM", "US", None, "high", None, 0.3, 0.2, "openbb"),
            ("macro", now + timedelta(days=3), "Retail Sales", "US", None, "medium", None, 0.4, 0.1, "openbb"),
            ("earnings", now + timedelta(days=2), "Earnings: AAPL Q4", "US", "AAPL", "high", None, 1.65, 1.50, "openbb"),
            ("earnings", now + timedelta(days=4), "Earnings: NVDA Q3", "US", "NVDA", "high", None, 0.75, 0.68, "openbb"),
            ("earnings", now + timedelta(days=5), "Earnings: MSFT Q2", "US", "MSFT", "high", None, 2.95, 2.80, "openbb"),
        ]
        for kind, ts_dt, title, country, ticker, importance, actual, forecast, previous, src in cal_items:
            db.insert_calendar_event(kind, _iso(ts_dt), title, country, ticker, importance, actual, forecast, previous, src)

        db.log_tool_call(
            agent="sentiment_analyst",
            tool="fetch_news",
            params={"symbol": "NVDA", "limit": 20},
            result={},
            error="Alpaca News API rate limit: 429 Too Many Requests (retry after 30s)",
            duration_ms=4500,
            chat_id=db.get_or_create_chat("sentiment_analyst", "news"),
            ts=_iso(now - timedelta(hours=1, minutes=15)),
        )
        db.log_tool_call(
            agent="technical_analyst",
            tool="indicators",
            params={},
            result={},
            duration_ms=110,
            compacted=True,
            chat_id=db.get_or_create_chat("technical_analyst", "AAPL"),
            ts=_iso(now - timedelta(days=95)),
        )

        # Uso e costi LLM (oggi e giorni scorsi)
        db.log_llm_call(
            agent="portfolio_manager",
            model="my-combo",
            tokens_in=1850,
            tokens_out=380,
            cost=0.085,
            duration_ms=1450,
            ts=_iso(now),
        )
        db.log_llm_call(
            agent="technical_analyst",
            model="my-combo",
            tokens_in=1200,
            tokens_out=220,
            cost=0.045,
            duration_ms=980,
            ts=_iso(now),
        )
        db.log_llm_call(
            agent="technical_analyst",
            model="my-combo",
            tokens_in=950,
            tokens_out=180,
            cost=0.035,
            duration_ms=820,
            ts=_iso(now),
        )
        db.log_llm_call(
            agent="market_analyst",
            model="my-combo",
            tokens_in=1400,
            tokens_out=310,
            cost=0.060,
            duration_ms=1120,
            ts=_iso(now),
        )
        db.log_llm_call(
            agent="risk_analyst",
            model="my-combo",
            tokens_in=800,
            tokens_out=150,
            cost=0.025,
            duration_ms=650,
            ts=_iso(now),
        )

        for d in range(1, 8):
            day_ts = now - timedelta(days=d)
            db.log_llm_call(
                agent="portfolio_manager",
                model="my-combo",
                tokens_in=3500,
                tokens_out=700,
                cost=0.150,
                duration_ms=2200,
                ts=_iso(day_ts.replace(hour=14, minute=30)),
            )
            db.log_llm_call(
                agent="technical_analyst",
                model="my-combo",
                tokens_in=2800,
                tokens_out=550,
                cost=0.110,
                duration_ms=1800,
                ts=_iso(day_ts.replace(hour=15, minute=0)),
            )
            db.log_llm_call(
                agent="market_analyst",
                model="my-combo",
                tokens_in=2200,
                tokens_out=420,
                cost=0.085,
                duration_ms=1500,
                ts=_iso(day_ts.replace(hour=10, minute=15)),
            )

        # ----------------------------------------------------------------------
        # Bridge Agent Scenario Seeding
        # ----------------------------------------------------------------------
        # Costi e chiamate LLM del Bridge
        db.log_llm_call(
            agent="bridge",
            model="my-combo",
            tokens_in=950,
            tokens_out=180,
            cost=0.035,
            duration_ms=620,
            ts=_iso(now - timedelta(minutes=25)),
        )
        db.log_llm_call(
            agent="bridge",
            model="my-combo",
            tokens_in=1400,
            tokens_out=260,
            cost=0.055,
            duration_ms=890,
            ts=_iso(now - timedelta(minutes=10)),
        )

        # Conversazione 1: Con agent_relay da Technical Analyst su AMD
        c1_id = db.create_bridge_conversation(
            title="Livelli e supporti AMD", created_ts=_iso(now - timedelta(minutes=40))
        )
        db.append_bridge_message(
            c1_id,
            "luca",
            "text",
            "Chiedi al Technical Analyst di verificare i livelli di supporto su AMD.",
            ts=_iso(now - timedelta(minutes=39)),
            context={"page": "terminale", "ticker": "AMD"},
            refs=[
                {"type": "ticker", "id": "AMD", "label": "AMD"},
                {"type": "agent", "id": "technical_analyst", "label": "Technical Analyst"},
            ],
        )
        db.append_bridge_message(
            c1_id,
            "bridge",
            "text",
            "Ho inoltrato la richiesta al Technical Analyst per conto tuo sulla chat AMD.",
            ts=_iso(now - timedelta(minutes=38)),
            refs=[{"type": "ticker", "id": "AMD", "label": "AMD"}],
        )
        db.append_bridge_message(
            c1_id,
            "technical_analyst",
            "agent_relay",
            "Supporto chiave confermato a 118.50$, RSI a 32 su candela 1h in ipervenduto con divergenza volumetrica.",
            ts=_iso(now - timedelta(minutes=36)),
            context={
                "page": "ufficio",
                "ticker": "AMD",
                "ref": {"type": "agent", "id": "technical_analyst"},
            },
            refs=[{"type": "ticker", "id": "AMD", "label": "AMD"}],
        )
        db.append_bridge_message(
            c1_id,
            "bridge",
            "text",
            "Il Technical Analyst ha risposto: conferma il supporto di AMD a 118.50$, evidenziando RSI a 32 e una divergenza rialzista su orario.",
            ts=_iso(now - timedelta(minutes=35)),
            refs=[
                {"type": "ticker", "id": "AMD", "label": "AMD"},
                {"type": "agent", "id": "technical_analyst", "label": "Technical Analyst"},
            ],
        )

        # Conversazione 2: Con azione 'pending' di close_position con preview
        c2_id = db.create_bridge_conversation(
            title="Riduzione esposizione semiconduttori",
            created_ts=_iso(now - timedelta(minutes=25)),
        )
        db.append_bridge_message(
            c2_id,
            "luca",
            "text",
            "Chiudi 10 azioni di NVDA a mercato per proteggere i profitti.",
            ts=_iso(now - timedelta(minutes=24)),
            context={"page": "portafoglio", "ticker": "NVDA"},
            refs=[{"type": "ticker", "id": "NVDA", "label": "NVDA"}],
        )
        act_preview = {
            "ok": True,
            "reasons": [],
            "detail": {
                "ticker": "NVDA",
                "qty": 10.0,
                "current_price": 181.0,
                "estimated_proceeds": 1810.0,
                "realized_pnl_estimate": 310.0,
            },
        }
        act_c2 = db.create_bridge_action(
            conversation_id=c2_id,
            command="close_position",
            payload={"ticker": "NVDA", "qty": 10.0, "order_type": "market"},
            summary="Chiudi 10 azioni di NVDA a mercato",
            capital=True,
            status="pending",
            preview=act_preview,
            created_ts=_iso(now - timedelta(minutes=23)),
        )
        db.append_bridge_message(
            c2_id,
            "bridge",
            "action",
            "Ho preparato la proposta di vendita parziale per 10 azioni di NVDA a mercato. L'azione tocca capitale ed è in attesa della tua conferma esplicita.",
            ts=_iso(now - timedelta(minutes=23)),
            action_id=act_c2,
            refs=[{"type": "ticker", "id": "NVDA", "label": "NVDA"}],
        )

        # Conversazione 3: Con un'azione eseguita e una respinta
        c3_id = db.create_bridge_conversation(
            title="Gestione posizioni tech", created_ts=_iso(now - timedelta(hours=3))
        )
        db.append_bridge_message(
            c3_id,
            "luca",
            "text",
            "Alza lo stop loss di MSFT a 415$.",
            ts=_iso(now - timedelta(hours=2, minutes=58)),
            refs=[{"type": "ticker", "id": "MSFT", "label": "MSFT"}],
        )
        act_c3_exec = db.create_bridge_action(
            conversation_id=c3_id,
            command="modify_exit",
            payload={"ticker": "MSFT", "stop_price": 415.0},
            summary="Modifica stop loss MSFT a 415.00$",
            capital=True,
            status="executed",
            result_reasons=[],
            created_ts=_iso(now - timedelta(hours=2, minutes=57)),
        )
        db.update_bridge_action(
            act_c3_exec,
            status="executed",
            decided_ts=_iso(now - timedelta(hours=2, minutes=50)),
            decided_by="luca",
        )
        db.append_bridge_message(
            c3_id,
            "bridge",
            "text",
            "Azione 'Modifica stop loss MSFT a 415.00$' confermata ed eseguita con successo.",
            ts=_iso(now - timedelta(hours=2, minutes=50)),
            action_id=act_c3_exec,
            refs=[{"type": "ticker", "id": "MSFT", "label": "MSFT"}],
        )
        db.append_bridge_message(
            c3_id,
            "luca",
            "text",
            "Rifiuta la proposta di acquisto su TSLA.",
            ts=_iso(now - timedelta(hours=1, minutes=30)),
            refs=[{"type": "ticker", "id": "TSLA", "label": "TSLA"}],
        )
        act_c3_dism = db.create_bridge_action(
            conversation_id=c3_id,
            command="decide_proposal",
            payload={
                "proposal_id": 1,
                "action": "reject",
                "reason": "Non allineato con preferenza corrente",
            },
            summary="Rifiuta proposta buy TSLA",
            capital=True,
            status="dismissed",
            created_ts=_iso(now - timedelta(hours=1, minutes=28)),
        )
        db.update_bridge_action(
            act_c3_dism,
            status="dismissed",
            decided_ts=_iso(now - timedelta(hours=1, minutes=20)),
            decided_by="luca",
        )
        db.append_bridge_message(
            c3_id,
            "bridge",
            "text",
            "Azione 'Rifiuta proposta buy TSLA' respinta.",
            ts=_iso(now - timedelta(hours=1, minutes=20)),
            action_id=act_c3_dism,
            refs=[{"type": "ticker", "id": "TSLA", "label": "TSLA"}],
        )

        # Conversazione 4: Archiviata
        c4_id = db.create_bridge_conversation(
            title="Analisi trimestrale AAPL",
            created_ts=_iso(now - timedelta(days=2)),
            archived=True,
        )
        db.append_bridge_message(
            c4_id,
            "luca",
            "text",
            "Come sono andati i margini nel report di AAPL?",
            ts=_iso(now - timedelta(days=2, hours=1)),
            refs=[{"type": "ticker", "id": "AAPL", "label": "AAPL"}],
        )
        db.append_bridge_message(
            c4_id,
            "bridge",
            "text",
            "I margini lordi di AAPL sono cresciuti al 46.2%, battendo le stime grazie ai ricavi del comparto Servizi.",
            ts=_iso(now - timedelta(days=2)),
            refs=[{"type": "ticker", "id": "AAPL", "label": "AAPL"}],
        )

        # Briefing State & Cache with items of EVERY type
        since_briefing = _iso(now - timedelta(hours=18))
        db.set_briefing_seen(since_briefing)

        # Ensure items of every type exist in the briefing window
        # 1. alert
        db.add_inbox(
            "alert",
            "Alert prezzo: NVDA ha toccato la resistenza a 182.50$",
            ts=_iso(now - timedelta(hours=2)),
        )
        # 2. agent_error
        db.add_inbox(
            "error",
            "Fallimento chiamata tool: Alpaca News API 429 Too Many Requests per sentiment_analyst",
            ts=_iso(now - timedelta(hours=1, minutes=15)),
        )
        # 3. halt and resume events
        db.connection.execute(
            "INSERT INTO events (ts, type, actor, subject, command_id, payload) VALUES (?, ?, ?, ?, ?, ?)",
            (
                _iso(now - timedelta(hours=4)),
                "halt.changed",
                "luca",
                "halt",
                None,
                json.dumps({"status": "halted", "reason": "Test volatilità pre-apertura"}),
            ),
        )
        db.connection.execute(
            "INSERT INTO events (ts, type, actor, subject, command_id, payload) VALUES (?, ?, ?, ?, ?, ?)",
            (
                _iso(now - timedelta(hours=3, minutes=50)),
                "halt.changed",
                "luca",
                "halt",
                None,
                json.dumps({"status": "resumed", "reason": "Condizioni rientrate"}),
            ),
        )

        db.connection.execute(
            """
            INSERT INTO briefing_state (key, value, updated_ts)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_ts = excluded.updated_ts
            """,
            (
                f"summary:{since_briefing}",
                "Nelle ultime 18 ore: 2 trade registrati su NVDA e MSFT, 1 ordine pendente di approvazione per AAPL, 1 proposta da valutare per TSLA. Alert su NVDA, trading halt temporaneo rientrato, e 1 errore rate-limit Alpaca News. Portafoglio stabile con P&L positivo di seduta. Technical Analyst conferma supporto AMD a 118.50$.",
                _iso(now - timedelta(minutes=5)),
            ),
        )

        _seed_configurazioni(rt, now)


def _seed_configurazioni(rt: Any, now: datetime) -> None:
    db = rt.office.db
    db.insert_settings_version("luca", "Configurazione iniziale base", {}, {"max_parallel": 3})
    db.insert_settings_version("luca", "Aumento concorrenza e budget", {"max_parallel": 3}, {"max_parallel": 4, "budgets.cycle_budget": 60})
    db.insert_settings_version("luca", "Richiesta cambio timeframe a 15m (in attesa di riavvio)", {"market.bar_timeframe": "1h"}, {"max_parallel": 4, "budgets.cycle_budget": 60, "market.bar_timeframe": "15m"})

    db.insert_prompt_version("portfolio_manager", "luca", "v1 iniziale", "Sei il Portfolio Manager v1.")
    db.insert_prompt_version("portfolio_manager", "luca", "v2 aggiornato risk limits", "Sei il Portfolio Manager v2 con focus sui rischi.")
    db.insert_prompt_version("market_analyst", "luca", "v1 market analyst", "Sei il Market Analyst v1.")

    from storage.secrets import SecretsManager
    sec_file = Path("data/dev_secrets.env")
    meta_file = Path("data/dev_secrets.meta.json")
    manager = SecretsManager(secrets_path=sec_file, meta_path=meta_file)
    manager.set("OMNIROUTE_API_KEY", "sk-mock-omni-9999", "luca", "setup dev")
    manager.record_test("OMNIROUTE_API_KEY", True, "Modelli OmniRoute elencati con successo")
    manager.record_test("ALPACA_API_KEY", False, "Impossibile connettersi ad Alpaca (chiavi non impostate)")

    db.add_inbox("error", "Job DataRefreshJob fallito: timeout nella chiamata OpenBB API", ts=_iso(now - timedelta(minutes=10)))

    from storage.backup import create_db_backup
    create_db_backup(db, backup_dir="data/backups", max_backups=5)
    create_db_backup(db, backup_dir="data/backups", max_backups=5)
