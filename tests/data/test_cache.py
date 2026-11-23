"""Tests for DB-first financial data layer (DataCache and refresh)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from data.cache import DataCache
from data.refresh import (
    adapt_fundamentals_provider,
    adapt_market_data_provider,
    adapt_news_provider,
    refresh_watchlist_and_portfolio,
)
from storage.office_db import OfficeDB

ET = ZoneInfo("America/New_York")


@pytest.fixture
def db(tmp_path: Path) -> OfficeDB:
    db_path = tmp_path / "test_data_office.db"
    office_db = OfficeDB(db_path)
    yield office_db
    office_db.close()


def test_schema_compatibility_adds_missing_columns(db: OfficeDB) -> None:
    cache = DataCache(db=db)
    # Check reported mismatches
    assert any("prices_ohlcv" in m and "stale" in m for m in cache.schema_mismatches)
    assert any("securities" in m and "source" in m for m in cache.schema_mismatches)

    # Verify column existence in db
    ohlcv_cols = {
        row[1] for row in db.connection.execute("PRAGMA table_info(prices_ohlcv)").fetchall()
    }
    assert "stale" in ohlcv_cols

    sec_cols = {
        row[1] for row in db.connection.execute("PRAGMA table_info(securities)").fetchall()
    }
    assert "source" in sec_cols
    assert "fetched_at" in sec_cols
    assert "stale" in sec_cols


def test_cache_get_and_upsert_ohlcv(db: OfficeDB) -> None:
    call_count = 0
    t0 = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)

    def fake_ohlcv(symbol: str, **kwargs):
        nonlocal call_count
        call_count += 1
        return [
            {
                "symbol": symbol,
                "ts": "2026-11-18T10:00:00Z",
                "interval": "1d",
                "o": 150.0,
                "h": 155.0,
                "l": 149.0,
                "c": 154.0,
                "v": 1000000.0,
                "source": "fake_feed",
            }
        ]

    cache = DataCache(
        db=db,
        providers={"prices_ohlcv": fake_ohlcv},
        clock=lambda: t0,
    )

    # 1. First get: fetch from provider and store in DB
    data1 = cache.get("prices_ohlcv", "AAPL", interval="1d")
    assert call_count == 1
    assert not data1.stale
    assert len(data1) == 1
    assert data1[0]["symbol"] == "AAPL"
    assert data1[0]["c"] == 154.0
    assert data1.source == "fake_feed"
    assert data1[0]["stale"] == 0

    # 2. Second get within TTL: cache hit, provider NOT called
    data2 = cache.get("prices_ohlcv", "AAPL", interval="1d")
    assert call_count == 1
    assert len(data2) == 1
    assert not data2.stale
    assert data2[0]["c"] == 154.0

    # 3. Deduplication: verify exactly 1 row exists in prices_ohlcv for AAPL
    rows = db.connection.execute("SELECT * FROM prices_ohlcv WHERE symbol = 'AAPL'").fetchall()
    assert len(rows) == 1


def test_cache_ohlcv_market_close_refresh(db: OfficeDB) -> None:
    call_count = 0
    # Wednesday 2026-11-18: 14:00 ET (19:00 UTC) -> market open
    simulated_now = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)

    def fake_ohlcv(symbol: str, **kwargs):
        nonlocal call_count
        call_count += 1
        return [
            {
                "symbol": symbol,
                "ts": "2026-11-18T16:00:00Z",
                "interval": "1d",
                "o": 100.0,
                "h": 110.0,
                "l": 95.0,
                "c": 105.0 + call_count,
                "v": 50000.0,
                "source": "alpaca",
            }
        ]

    cache = DataCache(
        db=db,
        providers={"prices_ohlcv": fake_ohlcv},
        clock=lambda: simulated_now,
    )

    # Fetch at 14:00 ET
    data1 = cache.get("prices_ohlcv", "MSFT")
    assert call_count == 1
    assert data1[0]["c"] == 106.0

    # Same day at 15:30 ET (20:30 UTC): still before close, should hit cache
    simulated_now = datetime(2026, 11, 18, 20, 30, tzinfo=UTC)
    data2 = cache.get("prices_ohlcv", "MSFT")
    assert call_count == 1
    assert data2[0]["c"] == 106.0

    # Same day at 16:30 ET (21:30 UTC): market closed at 16:00 ET, data was fetched before close!
    # Daily OHLCV must be refreshed after market close -> should fetch fresh
    simulated_now = datetime(2026, 11, 18, 21, 30, tzinfo=UTC)
    data3 = cache.get("prices_ohlcv", "MSFT")
    assert call_count == 2
    assert data3[0]["c"] == 107.0


def test_cache_fundamentals_and_ratings_weekly_ttl(db: OfficeDB) -> None:
    call_count = 0
    t0 = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    simulated_now = t0

    def fake_fundamentals(symbol: str, **kwargs):
        nonlocal call_count
        call_count += 1
        return {
            "source": "yahoo",
            "data": {"market_cap": 3000000000000, "pe_ratio": 28.5},
        }

    cache = DataCache(
        db=db,
        providers={"fundamentals": fake_fundamentals},
        clock=lambda: simulated_now,
    )

    # Initial fetch
    data1 = cache.get("fundamentals", "AAPL")
    assert call_count == 1
    assert not data1.stale
    assert data1[0]["data"]["pe_ratio"] == 28.5

    # 5 days later: within weekly TTL (7 days) -> cache hit
    simulated_now = t0 + timedelta(days=5)
    data2 = cache.get("fundamentals", "AAPL")
    assert call_count == 1
    assert not data2.stale

    # 8 days later: expired (> 7 days) -> fetches again
    simulated_now = t0 + timedelta(days=8)
    data3 = cache.get("fundamentals", "AAPL")
    assert call_count == 2
    assert not data3.stale


def test_cache_macro_series_frequency_ttls(db: OfficeDB) -> None:
    gdp_calls = 0
    cpi_calls = 0
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    simulated_now = t0

    def fake_macro(series_id: str, **kwargs):
        nonlocal gdp_calls, cpi_calls
        if series_id == "GDP":
            gdp_calls += 1
            return [{"series_id": "GDP", "ts": "2026-01-01", "value": 25000.0, "source": "fred"}]
        if series_id == "CPI":
            cpi_calls += 1
            return [{"series_id": "CPI", "ts": "2026-01-01", "value": 310.2, "source": "fred"}]
        return []

    cache = DataCache(
        db=db,
        providers={"macro_series": fake_macro},
        clock=lambda: simulated_now,
    )

    cache.get("macro_series", "GDP")
    cache.get("macro_series", "CPI")
    assert gdp_calls == 1
    assert cpi_calls == 1

    # 35 days later: CPI (monthly: 30d TTL) is expired, but GDP (quarterly: 90d TTL) is still fresh!
    simulated_now = t0 + timedelta(days=35)
    cache.get("macro_series", "GDP")
    assert gdp_calls == 1  # still fresh

    cache.get("macro_series", "CPI")
    assert cpi_calls == 2  # expired and refreshed


def test_stale_fallback_when_provider_fails(db: OfficeDB) -> None:
    should_fail = False
    simulated_now = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

    def fetcher(symbol: str, **kwargs):
        if should_fail:
            raise ConnectionError("Upstream API is unreachable")
        return {
            "source": "openbb",
            "data": {"rating": "BUY", "target_price": 200.0},
        }

    cache = DataCache(
        db=db,
        providers={"ratings": fetcher},
        clock=lambda: simulated_now,
    )

    # 1. Initial successful fetch
    initial = cache.get("ratings", "NVDA")
    assert not initial.stale
    assert initial[0]["data"]["rating"] == "BUY"

    # 2. Expire cache and simulate provider failure
    simulated_now += timedelta(days=10)
    should_fail = True

    # Cache should NOT raise: returns cached data flagged stale=True
    stale_res = cache.get("ratings", "NVDA")
    assert stale_res.stale is True
    assert stale_res["stale"] is True
    assert stale_res[0]["stale"] == 1
    assert stale_res[0]["data"]["rating"] == "BUY"

    # Verify DB column stale is set to 1
    row = db.connection.execute("SELECT stale FROM ratings WHERE symbol = 'NVDA'").fetchone()
    assert row["stale"] == 1

    # 3. Provider recovers
    should_fail = False
    recovered = cache.get("ratings", "NVDA")
    assert recovered.stale is False
    assert recovered[0]["stale"] == 0

    row = db.connection.execute("SELECT stale FROM ratings WHERE symbol = 'NVDA'").fetchone()
    assert row["stale"] == 0


def test_re_raise_when_nothing_cached_and_provider_fails(db: OfficeDB) -> None:
    def failing_fetcher(symbol: str, **kwargs):
        raise TimeoutError("Timeout contacting provider")

    cache = DataCache(
        db=db,
        providers={"news": failing_fetcher},
    )

    with pytest.raises(TimeoutError, match="Timeout contacting provider"):
        cache.get("news", "TSLA")


def test_indicators_not_stored(db: OfficeDB) -> None:
    cache = DataCache(db=db)
    with pytest.raises(ValueError, match="Indicators are not stored"):
        cache.get("indicators", "AAPL")


def test_earnings_and_insider_tables(db: OfficeDB) -> None:
    def fake_earnings(symbol: str, **kwargs):
        return [
            {"date": "2026-10-25", "eps_est": 1.2, "eps_act": 1.35, "source": "openbb"}
        ]

    def fake_insider(symbol: str, **kwargs):
        return [
            {
                "transaction_date": "2026-11-01",
                "insider_name": "Cook Tim",
                "shares": 10000,
                "source": "sec",
            }
        ]

    cache = DataCache(
        db=db,
        providers={"earnings": fake_earnings, "insider": fake_insider},
    )

    earnings = cache.get("earnings", "AAPL")
    assert len(earnings) == 1
    assert earnings[0]["data"]["eps_act"] == 1.35

    insider = cache.get("insider", "AAPL")
    assert len(insider) == 1
    assert insider[0]["data"]["insider_name"] == "Cook Tim"


def test_refresh_watchlist_and_portfolio(db: OfficeDB) -> None:
    # Set up watchlist and portfolio in db
    db.add_watchlist("AAPL", note="Top tech")
    db.add_watchlist("GOOGL", note="Search")
    db.insert_portfolio_snapshot(
        equity=100000.0,
        cash=50000.0,
        positions=[{"ticker": "NVDA", "qty": 100}],
    )

    fetched_symbols: set[str] = set()

    def fake_ohlcv(symbol: str, **kwargs):
        fetched_symbols.add(symbol)
        return [
            {
                "symbol": symbol,
                "ts": "2026-11-18T10:00:00Z",
                "interval": "1d",
                "o": 100.0,
                "h": 105.0,
                "l": 99.0,
                "c": 104.0,
                "v": 10000.0,
                "source": "fake",
            }
        ]

    cache = DataCache(
        db=db,
        providers={"prices_ohlcv": fake_ohlcv},
    )

    # Pre-fetch for all watchlist + portfolio tickers
    report = refresh_watchlist_and_portfolio(cache=cache)
    assert sorted(report["tickers"]) == ["AAPL", "GOOGL", "NVDA"]
    assert fetched_symbols == {"AAPL", "GOOGL", "NVDA"}
    assert report["refreshed"] == 3
    assert report["errors"] == []

    # Second call without force: already fresh -> refreshed count is still 3 (cache hit returns ok)
    report2 = refresh_watchlist_and_portfolio(cache=cache, force=False)
    assert report2["errors"] == []


def test_adapter_protocols_with_fake_providers(db: OfficeDB) -> None:
    class FakeMarketDataProvider:
        def get_ohlcv_history(
            self, symbol: str, start: datetime, end: datetime, interval: str = "1d"
        ):
            return [
                {
                    "symbol": symbol,
                    "ts": start.isoformat(),
                    "interval": interval,
                    "o": 200.0,
                    "h": 205.0,
                    "l": 195.0,
                    "c": 202.0,
                    "v": 12345.0,
                    "source": "adapter_market",
                }
            ]

    class FakeFundamentalsProvider:
        def get_fundamentals(self, symbol: str):
            return {
                "source": "adapter_fund",
                "data": {"roe": 0.35, "market_cap": 2000000000000},
            }

    class FakeNewsProvider:
        def get_news(self, symbol: str, start: datetime, end: datetime):
            return [
                {
                    "headline": f"{symbol} reports record revenue",
                    "summary": "Revenue up 20%",
                    "published_at": start.isoformat(),
                    "source": "adapter_news",
                }
            ]

    cache = DataCache(
        db=db,
        providers={
            "prices_ohlcv": adapt_market_data_provider(FakeMarketDataProvider()),
            "fundamentals": adapt_fundamentals_provider(FakeFundamentalsProvider()),
            "news": adapt_news_provider(FakeNewsProvider()),
        },
    )

    ohlcv = cache.get("prices_ohlcv", "AMZN")
    assert len(ohlcv) == 1
    assert ohlcv[0]["source"] == "adapter_market"

    fund = cache.get("fundamentals", "AMZN")
    assert fund[0]["data"]["roe"] == 0.35

    news = cache.get("news", "AMZN")
    assert "reports record revenue" in news[0]["headline"]
