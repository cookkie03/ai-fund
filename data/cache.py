"""DB-first financial data cache backed by OfficeDB.

Implements DataCache with per-kind TTL policies, provider injection,
upserting without duplicates, and graceful stale fallback on provider failure.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from storage.office_db import OfficeDB

ET = ZoneInfo("America/New_York")

# 11 supported financial tables in OfficeDB
SUPPORTED_KINDS: frozenset[str] = frozenset(
    {
        "prices_ohlcv",
        "fundamentals",
        "ratios",
        "earnings",
        "ratings",
        "insider",
        "news",
        "macro_series",
        "econ_calendar",
        "sector_performance",
        "securities",
    }
)

# Default TTLs per spec:
# - OHLCV: daily (and refreshed after market close 16:00 ET)
# - calendar, news: daily
# - fundamentals, ratings, ratios: weekly
# - earnings, insider: daily
# - sector_performance: daily
# - securities: 30 days
# - macro_series: default 30 days or by series frequency
DEFAULT_TTLS: dict[str, timedelta] = {
    "prices_ohlcv": timedelta(days=1),
    "news": timedelta(days=1),
    "econ_calendar": timedelta(days=1),
    "fundamentals": timedelta(days=7),
    "ratings": timedelta(days=7),
    "ratios": timedelta(days=7),
    "earnings": timedelta(days=1),
    "insider": timedelta(days=1),
    "sector_performance": timedelta(days=1),
    "securities": timedelta(days=30),
    "macro_series": timedelta(days=30),
}

# Known macro series frequencies
MACRO_SERIES_FREQUENCIES: dict[str, timedelta] = {
    "GDP": timedelta(days=90),
    "GDPC1": timedelta(days=90),
    "CPI": timedelta(days=30),
    "CPIAUCSL": timedelta(days=30),
    "UNRATE": timedelta(days=30),
    "PAYEMS": timedelta(days=30),
    "FEDFUNDS": timedelta(days=30),
    "PPI": timedelta(days=30),
    "DGS10": timedelta(days=1),
    "DGS2": timedelta(days=1),
    "T10Y2Y": timedelta(days=1),
    "ICSA": timedelta(days=7),
}


class CachedData(list):
    """List of cached row records with metadata and convenient accessors."""

    def __init__(
        self,
        items: Iterable[dict[str, Any]] = (),
        stale: bool = False,
        source: str = "",
        fetched_at: str = "",
        kind: str = "",
        key: str | None = None,
    ) -> None:
        super().__init__(items)
        self.stale = stale
        self.source = source
        self.fetched_at = fetched_at
        self.kind = kind
        self.key = key

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, str):
            if item == "stale":
                return self.stale
            if item == "source":
                return self.source
            if item == "fetched_at":
                return self.fetched_at
            if item == "data":
                return list(self)
            if len(self) > 0 and isinstance(super().__getitem__(0), dict):
                first = super().__getitem__(0)
                if item in first:
                    return first[item]
            raise KeyError(item)
        return super().__getitem__(item)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except (KeyError, IndexError):
            return default


def ensure_schema_compatibility(conn: sqlite3.Connection) -> list[str]:
    """Check OfficeDB schema and dynamically add any missing columns.

    Returns a list of schema mismatch messages describing added columns.
    """
    mismatches: list[str] = []

    # 1. prices_ohlcv: check for stale column
    ohlcv_cols = {row[1] for row in conn.execute("PRAGMA table_info(prices_ohlcv)").fetchall()}
    if "stale" not in ohlcv_cols:
        conn.execute("ALTER TABLE prices_ohlcv ADD COLUMN stale INTEGER NOT NULL DEFAULT 0")
        mismatches.append("prices_ohlcv: added missing 'stale' column")

    # 2. securities: check for source, fetched_at, stale
    sec_cols = {row[1] for row in conn.execute("PRAGMA table_info(securities)").fetchall()}
    if "source" not in sec_cols:
        conn.execute("ALTER TABLE securities ADD COLUMN source TEXT NOT NULL DEFAULT ''")
        mismatches.append("securities: added missing 'source' column")
    if "fetched_at" not in sec_cols:
        conn.execute("ALTER TABLE securities ADD COLUMN fetched_at TEXT NOT NULL DEFAULT ''")
        mismatches.append("securities: added missing 'fetched_at' column")
    if "stale" not in sec_cols:
        conn.execute("ALTER TABLE securities ADD COLUMN stale INTEGER NOT NULL DEFAULT 0")
        mismatches.append("securities: added missing 'stale' column")

    return mismatches


class DataCache:
    """DB-first financial data cache.

    Reads data from OfficeDB tables. If missing or expired according to the TTL
    policy, calls the injected provider, upserts without duplicates, and records
    source and fetched_at. If fetch fails and cached data exists, returns cached data
    flagged stale=True; if nothing cached, re-raises the failure.
    Indicators are NOT stored.
    """

    def __init__(
        self,
        db: OfficeDB,
        providers: Mapping[str, Callable[..., Any]] | None = None,
        clock: Callable[[], datetime] | None = None,
        ttl_policy: Mapping[str, timedelta | int | float] | None = None,
    ) -> None:
        self.db = db
        self.providers: dict[str, Callable[..., Any]] = dict(providers or {})
        self.clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self.ttl_policy: dict[str, timedelta | int | float] = dict(ttl_policy or {})
        self.schema_mismatches = ensure_schema_compatibility(self.db.connection)

    def _now_iso(self) -> str:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return now.isoformat().replace("+00:00", "Z")

    def get(
        self,
        kind: str,
        key: str | None = None,
        force: bool = False,
        **kwargs: Any,
    ) -> CachedData:
        """Get financial data for kind and key, fetching via provider if missing or expired."""
        if kind == "indicators":
            raise ValueError(
                "Indicators are not stored in cache; calculate on the fly from OHLCV bars."
            )
        if kind not in SUPPORTED_KINDS:
            raise ValueError(
                f"Unsupported data kind: {kind}. Supported kinds: {sorted(SUPPORTED_KINDS)}"
            )

        cached_rows = self._read_db(kind, key, **kwargs)
        is_missing = len(cached_rows) == 0

        expired = force or is_missing or self._is_expired(kind, key, cached_rows)
        has_stale_flag = any(bool(r.get("stale", 0)) for r in cached_rows)

        # Fresh cache hit
        if not expired and not has_stale_flag:
            return self._format_result(kind, key, cached_rows, stale=False)

        # Needs fetch
        fetcher = self.providers.get(kind)
        if fetcher is None:
            if cached_rows:
                return self._format_result(kind, key, cached_rows, stale=expired or has_stale_flag)
            raise KeyError(f"No provider registered for kind '{kind}' and no cached data exists.")

        try:
            raw_data = self._call_fetcher(fetcher, key, **kwargs)
            self._upsert(kind, key, raw_data, **kwargs)
            fresh_rows = self._read_db(kind, key, **kwargs)
            return self._format_result(kind, key, fresh_rows, stale=False)
        except Exception:
            if cached_rows:
                self._mark_stale(kind, key)
                stale_rows = self._read_db(kind, key, **kwargs)
                return self._format_result(kind, key, stale_rows, stale=True)
            raise

    def _call_fetcher(
        self, fetcher: Callable[..., Any], key: str | None, **kwargs: Any
    ) -> Any:
        if key is not None:
            try:
                return fetcher(key, **kwargs)
            except TypeError:
                pass
        return fetcher(**kwargs)

    def _read_db(self, kind: str, key: str | None, **kwargs: Any) -> list[dict[str, Any]]:
        conn = self.db.connection
        key_col = self._key_column(kind)

        params: list[Any] = []
        where_clauses: list[str] = []

        if key is not None and key_col is not None:
            where_clauses.append(f"{key_col} = ?")
            params.append(key)

        if kind == "prices_ohlcv" and "interval" in kwargs:
            where_clauses.append("interval = ?")
            params.append(kwargs["interval"])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        order_sql = self._order_clause(kind)

        query = f"SELECT * FROM {kind} {where_sql} {order_sql}"
        rows = conn.execute(query, params).fetchall()

        result: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            if "data_json" in d and d["data_json"]:
                try:
                    d["data"] = json.loads(d["data_json"])
                except Exception:
                    pass
            if "perf_json" in d and d["perf_json"]:
                try:
                    d["perf"] = json.loads(d["perf_json"])
                except Exception:
                    pass
            result.append(d)
        return result

    def _order_clause(self, kind: str) -> str:
        if kind == "prices_ohlcv":
            return "ORDER BY ts ASC"
        if kind == "macro_series":
            return "ORDER BY ts ASC"
        if kind == "econ_calendar":
            return "ORDER BY event_ts ASC"
        if kind == "news":
            return "ORDER BY published_at DESC"
        if kind == "earnings":
            return "ORDER BY date DESC"
        if kind == "insider":
            return "ORDER BY transaction_date DESC"
        return "ORDER BY id DESC" if kind != "securities" else ""

    def _key_column(self, kind: str) -> str | None:
        if kind in (
            "prices_ohlcv",
            "fundamentals",
            "ratios",
            "earnings",
            "ratings",
            "insider",
            "news",
            "securities",
        ):
            return "symbol"
        if kind == "macro_series":
            return "series_id"
        if kind == "econ_calendar":
            return "event_id"
        if kind == "sector_performance":
            return "sector"
        return None

    def _is_expired(
        self, kind: str, key: str | None, rows: list[dict[str, Any]]
    ) -> bool:
        if not rows:
            return True

        fetched_dates = [r["fetched_at"] for r in rows if r.get("fetched_at")]
        if not fetched_dates:
            return True

        latest_str = max(fetched_dates)
        try:
            latest_dt = datetime.fromisoformat(latest_str)
        except ValueError:
            return True

        if latest_dt.tzinfo is None:
            latest_dt = latest_dt.replace(tzinfo=UTC)

        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        ttl = self._resolve_ttl(kind, key)

        if kind == "prices_ohlcv":
            now_et = now.astimezone(ET)
            fetched_et = latest_dt.astimezone(ET)

            if now_et.date() > fetched_et.date():
                if now_et.weekday() < 5 and (
                    now_et.hour > 16 or (now_et.hour == 16 and now_et.minute >= 0)
                ):
                    return True
                if now - latest_dt >= ttl:
                    return True
            elif now_et.date() == fetched_et.date():
                if now_et.weekday() < 5:
                    is_now_after_close = now_et.hour > 16 or (
                        now_et.hour == 16 and now_et.minute >= 0
                    )
                    was_fetched_before_close = fetched_et.hour < 16
                    if is_now_after_close and was_fetched_before_close:
                        return True

        return (now - latest_dt) >= ttl

    def _resolve_ttl(self, kind: str, key: str | None) -> timedelta:
        if key and f"{kind}:{key}" in self.ttl_policy:
            val = self.ttl_policy[f"{kind}:{key}"]
            return timedelta(seconds=val) if isinstance(val, (int, float)) else val

        if kind in self.ttl_policy:
            val = self.ttl_policy[kind]
            return timedelta(seconds=val) if isinstance(val, (int, float)) else val

        if kind == "macro_series" and key in MACRO_SERIES_FREQUENCIES:
            return MACRO_SERIES_FREQUENCIES[key]

        return DEFAULT_TTLS.get(kind, timedelta(days=1))

    def _mark_stale(self, kind: str, key: str | None) -> None:
        conn = self.db.connection
        key_col = self._key_column(kind)
        if key is not None and key_col is not None:
            conn.execute(f"UPDATE {kind} SET stale = 1 WHERE {key_col} = ?", (key,))
        else:
            conn.execute(f"UPDATE {kind} SET stale = 1")

    def _upsert(self, kind: str, key: str | None, raw_data: Any, **kwargs: Any) -> None:
        now_iso = self._now_iso()
        conn = self.db.connection
        key_col = self._key_column(kind)
        if key is not None and key_col is not None:
            conn.execute(f"UPDATE {kind} SET stale = 0 WHERE {key_col} = ?", (key,))

        if kind == "prices_ohlcv":
            bars = raw_data if isinstance(raw_data, (list, tuple)) else [raw_data]
            for bar in bars:
                symbol = getattr(bar, "symbol", None) or (
                    bar.get("symbol") if isinstance(bar, dict) else key
                )
                ts_val = getattr(bar, "timestamp", None) or (
                    bar.get("timestamp") or bar.get("ts") or bar.get("date")
                    if isinstance(bar, dict)
                    else None
                )
                if isinstance(ts_val, datetime):
                    ts = ts_val.isoformat().replace("+00:00", "Z")
                else:
                    ts = str(ts_val)

                interval = getattr(bar, "interval", None) or (
                    bar.get("interval") if isinstance(bar, dict) else kwargs.get("interval", "1d")
                )
                o = float(
                    getattr(bar, "open", None)
                    if hasattr(bar, "open")
                    else (bar.get("open", bar.get("o", 0.0)) if isinstance(bar, dict) else 0.0)
                )
                h = float(
                    getattr(bar, "high", None)
                    if hasattr(bar, "high")
                    else (bar.get("high", bar.get("h", 0.0)) if isinstance(bar, dict) else 0.0)
                )
                low_val = float(
                    getattr(bar, "low", None)
                    if hasattr(bar, "low")
                    else (bar.get("low", bar.get("l", 0.0)) if isinstance(bar, dict) else 0.0)
                )
                c = float(
                    getattr(bar, "close", None)
                    if hasattr(bar, "close")
                    else (bar.get("close", bar.get("c", 0.0)) if isinstance(bar, dict) else 0.0)
                )
                v = float(
                    getattr(bar, "volume", None)
                    if hasattr(bar, "volume")
                    else (bar.get("volume", bar.get("v", 0.0)) if isinstance(bar, dict) else 0.0)
                )
                source = getattr(bar, "source", None) or (
                    bar.get("source") if isinstance(bar, dict) else "provider"
                )

                conn.execute(
                    """
                    INSERT INTO prices_ohlcv (
                        symbol, ts, interval, o, h, l, c, v, source, fetched_at, stale
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(symbol, ts, interval) DO UPDATE SET
                        o = excluded.o,
                        h = excluded.h,
                        l = excluded.l,
                        c = excluded.c,
                        v = excluded.v,
                        source = excluded.source,
                        fetched_at = excluded.fetched_at,
                        stale = 0
                    """,
                    (symbol, ts, interval, o, h, low_val, c, v, source, now_iso),
                )

        elif kind in ("fundamentals", "ratios", "ratings"):
            symbol = key
            source = "provider"
            data_dict = raw_data
            if isinstance(raw_data, dict):
                source = raw_data.get("source", "provider")
                data_dict = raw_data.get("data", raw_data)
            elif isinstance(raw_data, (list, tuple)):
                data_dict = {}
                for obs in raw_data:
                    metric = getattr(obs, "metric", None) or (
                        obs.get("metric") if isinstance(obs, dict) else str(obs)
                    )
                    val = getattr(obs, "value", None) or (
                        obs.get("value") if isinstance(obs, dict) else None
                    )
                    source = getattr(obs, "source", source) or (
                        obs.get("source", source) if isinstance(obs, dict) else source
                    )
                    data_dict[str(metric)] = str(val) if val is not None else ""

            data_json = json.dumps(data_dict, default=str)
            conn.execute(
                f"""
                INSERT INTO {kind} (symbol, source, fetched_at, stale, data_json)
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT(symbol, source, fetched_at) DO UPDATE SET
                    data_json = excluded.data_json,
                    stale = 0
                """,
                (symbol, source, now_iso, data_json),
            )

        elif kind == "earnings":
            items = raw_data if isinstance(raw_data, (list, tuple)) else [raw_data]
            for item in items:
                date_str = (
                    item.get("date", now_iso[:10])
                    if isinstance(item, dict)
                    else now_iso[:10]
                )
                source = item.get("source", "provider") if isinstance(item, dict) else "provider"
                data_json = json.dumps(item, default=str)
                conn.execute(
                    """
                    INSERT INTO earnings (symbol, date, source, fetched_at, stale, data_json)
                    VALUES (?, ?, ?, ?, 0, ?)
                    ON CONFLICT(symbol, date, source) DO UPDATE SET
                        fetched_at = excluded.fetched_at,
                        stale = 0,
                        data_json = excluded.data_json
                    """,
                    (key, date_str, source, now_iso, data_json),
                )

        elif kind == "insider":
            items = raw_data if isinstance(raw_data, (list, tuple)) else [raw_data]
            for item in items:
                tx_date = (
                    item.get("transaction_date", item.get("date", now_iso[:10]))
                    if isinstance(item, dict)
                    else now_iso[:10]
                )
                source = item.get("source", "provider") if isinstance(item, dict) else "provider"
                data_json = json.dumps(item, default=str)
                conn.execute(
                    """
                    INSERT INTO insider (
                        symbol, transaction_date, source, fetched_at, stale, data_json
                    ) VALUES (?, ?, ?, ?, 0, ?)
                    ON CONFLICT(symbol, transaction_date, source, fetched_at) DO UPDATE SET
                        data_json = excluded.data_json,
                        stale = 0
                    """,
                    (key, tx_date, source, now_iso, data_json),
                )

        elif kind == "news":
            items = raw_data if isinstance(raw_data, (list, tuple)) else [raw_data]
            for item in items:
                headline = getattr(item, "headline", None) or (
                    item.get("headline", "") if isinstance(item, dict) else str(item)
                )
                summary = getattr(item, "summary", None) or (
                    item.get("summary", "") if isinstance(item, dict) else ""
                )
                full_text = getattr(item, "full_text", None) or (
                    item.get("full_text", "") if isinstance(item, dict) else ""
                )
                pub_at = getattr(item, "published_at", None) or (
                    item.get("published_at", now_iso) if isinstance(item, dict) else now_iso
                )
                if isinstance(pub_at, datetime):
                    pub_at = pub_at.isoformat().replace("+00:00", "Z")
                source = getattr(item, "source", None) or (
                    item.get("source", "provider") if isinstance(item, dict) else "provider"
                )
                sym = getattr(item, "symbol", None) or (
                    item.get("symbol", key) if isinstance(item, dict) else key
                )
                conn.execute(
                    """
                    INSERT INTO news (
                        symbol, headline, summary, full_text,
                        published_at, source, fetched_at, stale
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(symbol, published_at, headline) DO UPDATE SET
                        summary = excluded.summary,
                        full_text = excluded.full_text,
                        source = excluded.source,
                        fetched_at = excluded.fetched_at,
                        stale = 0
                    """,
                    (sym, headline, summary, full_text, str(pub_at), source, now_iso),
                )

        elif kind == "macro_series":
            series_id = key
            items = raw_data if isinstance(raw_data, (list, tuple)) else [raw_data]
            for item in items:
                sid = (
                    item.get("series_id", series_id) if isinstance(item, dict) else series_id
                )
                ts_val = (
                    item.get("ts", item.get("date", now_iso[:10]))
                    if isinstance(item, dict)
                    else now_iso[:10]
                )
                if isinstance(ts_val, datetime):
                    ts_val = ts_val.isoformat().replace("+00:00", "Z")
                val = float(
                    item.get("value", item.get("val", 0.0))
                    if isinstance(item, dict)
                    else float(item)
                )
                source = item.get("source", "provider") if isinstance(item, dict) else "provider"
                conn.execute(
                    """
                    INSERT INTO macro_series (series_id, ts, value, source, fetched_at, stale)
                    VALUES (?, ?, ?, ?, ?, 0)
                    ON CONFLICT(series_id, ts) DO UPDATE SET
                        value = excluded.value,
                        source = excluded.source,
                        fetched_at = excluded.fetched_at,
                        stale = 0
                    """,
                    (sid, str(ts_val), val, source, now_iso),
                )

        elif kind == "econ_calendar":
            items = raw_data if isinstance(raw_data, (list, tuple)) else [raw_data]
            for item in items:
                name = (
                    item.get("event_name", item.get("name", "Event"))
                    if isinstance(item, dict)
                    else str(item)
                )
                ts = (
                    item.get("event_ts", item.get("ts", now_iso))
                    if isinstance(item, dict)
                    else now_iso
                )
                event_id = (
                    item.get("event_id", item.get("id", f"{name}_{ts}"))
                    if isinstance(item, dict)
                    else f"{name}_{ts}"
                )
                impact = item.get("impact", "medium") if isinstance(item, dict) else "medium"
                source = item.get("source", "provider") if isinstance(item, dict) else "provider"
                data_json = json.dumps(item, default=str)
                conn.execute(
                    """
                    INSERT INTO econ_calendar (
                        event_id, event_name, event_ts, impact, source, fetched_at, stale, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                    ON CONFLICT(event_id, source) DO UPDATE SET
                        event_name = excluded.event_name,
                        event_ts = excluded.event_ts,
                        impact = excluded.impact,
                        fetched_at = excluded.fetched_at,
                        stale = 0,
                        data_json = excluded.data_json
                    """,
                    (event_id, name, str(ts), impact, source, now_iso, data_json),
                )

        elif kind == "sector_performance":
            items = raw_data if isinstance(raw_data, (list, tuple)) else [raw_data]
            for item in items:
                sector = (
                    item.get("sector", key or "All")
                    if isinstance(item, dict)
                    else (key or "All")
                )
                ts = item.get("ts", now_iso[:10]) if isinstance(item, dict) else now_iso[:10]
                source = item.get("source", "provider") if isinstance(item, dict) else "provider"
                perf_json = json.dumps(item.get("perf", item), default=str)
                conn.execute(
                    """
                    INSERT INTO sector_performance (
                        sector, ts, perf_json, source, fetched_at, stale
                    ) VALUES (?, ?, ?, ?, ?, 0)
                    ON CONFLICT(sector, ts, source) DO UPDATE SET
                        perf_json = excluded.perf_json,
                        fetched_at = excluded.fetched_at,
                        stale = 0
                    """,
                    (sector, str(ts), perf_json, source, now_iso),
                )

        elif kind == "securities":
            item = raw_data if isinstance(raw_data, dict) else {}
            sym = key or item.get("symbol", "")
            name = item.get("name", sym)
            sector = item.get("sector", "")
            industry = item.get("industry", "")
            source = item.get("source", "provider")
            conn.execute(
                """
                INSERT INTO securities (symbol, name, sector, industry, source, fetched_at, stale)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    sector = excluded.sector,
                    industry = excluded.industry,
                    source = excluded.source,
                    fetched_at = excluded.fetched_at,
                    stale = 0
                """,
                (sym, name, sector, industry, source, now_iso),
            )

    def _format_result(
        self,
        kind: str,
        key: str | None,
        rows: list[dict[str, Any]],
        stale: bool,
    ) -> CachedData:
        for r in rows:
            r["stale"] = stale
        source = rows[0].get("source", "") if rows else ""
        fetched_at = rows[0].get("fetched_at", "") if rows else ""
        return CachedData(
            items=rows,
            stale=stale,
            source=source,
            fetched_at=fetched_at,
            kind=kind,
            key=key,
        )
