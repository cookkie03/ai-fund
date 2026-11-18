"""Data refresh routines and provider adapter protocols.

Pre-fetches financial data for watchlist and portfolio according to per-kind TTLs.
Reuses existing providers (openbb, alpaca, yahoo) ONLY via adapter protocols,
without importing heavy SDKs at module import time.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from .cache import DataCache


class MarketDataProtocol(Protocol):
    """Protocol for OHLCV market data providers."""

    def get_ohlcv_history(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> Any: ...


class FundamentalsProtocol(Protocol):
    """Protocol for fundamental data providers."""

    def get_fundamentals(self, symbol: str) -> Any: ...


class NewsProtocol(Protocol):
    """Protocol for news data providers."""

    def get_news(self, symbol: str, start: datetime, end: datetime) -> Any: ...


def adapt_market_data_provider(provider: Any) -> Callable[..., Any]:
    """Wrap a MarketDataProtocol instance into a DataCache fetcher callable."""

    def fetcher(symbol: str, **kwargs: Any) -> Any:
        interval = kwargs.get("interval", "1d")
        now = datetime.now(UTC)
        start = kwargs.get("start")
        end = kwargs.get("end")
        if end is None:
            end = now
        if start is None:
            # Default to 30 days of history for pre-fetch
            start = end - (
                kwargs.get("delta")
                if "delta" in kwargs
                else datetime.resolution * 0
                + (
                    datetime.fromtimestamp(end.timestamp() - 30 * 86400, tz=UTC)
                    - datetime.fromtimestamp(0, tz=UTC)
                )
            )
        return provider.get_ohlcv_history(symbol=symbol, start=start, end=end, interval=interval)

    return fetcher


def adapt_fundamentals_provider(provider: Any) -> Callable[..., Any]:
    """Wrap a FundamentalsProtocol instance into a DataCache fetcher callable."""

    def fetcher(symbol: str, **kwargs: Any) -> Any:
        if hasattr(provider, "get_fundamentals"):
            return provider.get_fundamentals(symbol)
        if callable(provider):
            return provider(symbol, **kwargs)
        raise ValueError(f"Object {provider} cannot be adapted as a fundamentals provider")

    return fetcher


def adapt_news_provider(provider: Any) -> Callable[..., Any]:
    """Wrap a NewsProtocol instance into a DataCache fetcher callable."""

    def fetcher(symbol: str, **kwargs: Any) -> Any:
        now = datetime.now(UTC)
        start = kwargs.get("start")
        end = kwargs.get("end") or now
        if start is None:
            start = datetime.fromtimestamp(end.timestamp() - 7 * 86400, tz=UTC)
        if hasattr(provider, "get_news"):
            return provider.get_news(symbol=symbol, start=start, end=end)
        if callable(provider):
            return provider(symbol, start=start, end=end, **kwargs)
        raise ValueError(f"Object {provider} cannot be adapted as a news provider")

    return fetcher


TICKER_KINDS: tuple[str, ...] = (
    "prices_ohlcv",
    "news",
    "fundamentals",
    "ratings",
    "ratios",
    "earnings",
    "insider",
    "securities",
)

MARKET_KINDS: tuple[str, ...] = (
    "econ_calendar",
    "sector_performance",
)


def refresh_watchlist_and_portfolio(
    cache: DataCache,
    tickers: Sequence[str] | Iterable[str] | None = None,
    force: bool = False,
    kinds: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Pre-fetch financial data for watchlist and portfolio tickers according to TTLs.

    Used by the 'data refresh' CLI command and scheduled daily/weekly jobs.
    If tickers is None, discovers tickers from watchlist and portfolio snapshots in OfficeDB.
    """
    if tickers is not None:
        target_tickers = sorted(set(t.strip().upper() for t in tickers if t and t.strip()))
    else:
        # Discover from watchlist and portfolio in db
        db_tickers: set[str] = set()
        for w in cache.db.list_watchlist():
            t = w.get("ticker", "").strip().upper()
            if t:
                db_tickers.add(t)

        snapshot = cache.db.latest_portfolio_snapshot()
        if snapshot and snapshot.get("positions_json"):
            try:
                positions = json.loads(snapshot["positions_json"])
                for p in positions:
                    if isinstance(p, dict):
                        sym = p.get("ticker") or p.get("symbol")
                        if sym:
                            db_tickers.add(str(sym).strip().upper())
            except Exception:
                pass
        target_tickers = sorted(db_tickers)

    selected_ticker_kinds = [
        k for k in TICKER_KINDS if kinds is None or k in kinds
    ]
    selected_market_kinds = [
        k for k in MARKET_KINDS if kinds is None or k in kinds
    ]

    refreshed = 0
    stale = 0
    skipped = 0
    errors: list[dict[str, Any]] = []
    results: dict[str, dict[str, str]] = {}

    for ticker in target_tickers:
        results[ticker] = {}
        for kind in selected_ticker_kinds:
            if kind not in cache.providers:
                skipped += 1
                continue
            try:
                cached = cache.get(kind, key=ticker, force=force)
                if cached.stale:
                    stale += 1
                    results[ticker][kind] = "stale"
                else:
                    refreshed += 1
                    results[ticker][kind] = "ok"
            except Exception as exc:
                errors.append({"ticker": ticker, "kind": kind, "error": str(exc)})
                results[ticker][kind] = f"error: {exc}"

    for kind in selected_market_kinds:
        if kind not in cache.providers:
            skipped += 1
            continue
        try:
            cached = cache.get(kind, key=None, force=force)
            if cached.stale:
                stale += 1
            else:
                refreshed += 1
        except Exception as exc:
            errors.append({"ticker": None, "kind": kind, "error": str(exc)})

    return {
        "tickers": target_tickers,
        "refreshed": refreshed,
        "stale": stale,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }
