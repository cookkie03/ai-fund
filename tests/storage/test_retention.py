"""Tests for storage/retention.py pure downsampling/retention functions."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from storage.retention import (
    Bar,
    LlmRecord,
    NewsItem,
    RetentionPolicy,
    compact_llm_records,
    compact_news,
    downsample_daily_bars,
    downsample_hourly,
)


def test_empty_inputs():
    today = date(2026, 11, 18)
    assert downsample_daily_bars([], today) == []
    assert downsample_hourly([], today) == []
    assert compact_news([], today) == []
    assert compact_llm_records([], today) == []


def test_downsample_daily_bars_boundaries_and_aggregation():
    today = date(2026, 11, 18)  # Wednesday
    policy = RetentionPolicy(daily_years=5, weekly_years=10)
    # cutoff_daily: 2021-11-18 (Thursday)
    # cutoff_weekly: 2016-11-18 (Friday)

    # 1. Recent bar (< 5 years): 2021-11-19
    recent_bar = Bar(
        symbol="AAPL",
        ts=date(2021, 11, 19),
        open=Decimal("150"),
        high=Decimal("155"),
        low=Decimal("149"),
        close=Decimal("153"),
        volume=1000,
    )

    # 2. Exactly at 5y cutoff (2021-11-18) -> aggregated weekly
    # Week of 2021-11-15 (Monday) to 2021-11-19:
    # 2021-11-17 (Wed) & 2021-11-18 (Thu) are <= cutoff_daily
    w_bar1 = Bar(
        symbol="AAPL",
        ts=date(2021, 11, 17),
        open=Decimal("140"),
        high=Decimal("145"),
        low=Decimal("138"),
        close=Decimal("142"),
        volume=500,
    )
    w_bar2 = Bar(
        symbol="AAPL",
        ts=date(2021, 11, 18),
        open=Decimal("142"),
        high=Decimal("148"),
        low=Decimal("141"),
        close=Decimal("146"),
        volume=600,
    )

    # 3. Exactly at 10y cutoff (2016-11-18) and older in same month -> aggregated monthly
    m_bar1 = Bar(
        symbol="AAPL",
        ts=date(2016, 11, 10),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("99"),
        close=Decimal("102"),
        volume=2000,
    )
    m_bar2 = Bar(
        symbol="AAPL",
        ts=date(2016, 11, 18),
        open=Decimal("102"),
        high=Decimal("108"),
        low=Decimal("101"),
        close=Decimal("107"),
        volume=3000,
    )

    bars = [m_bar2, w_bar2, recent_bar, m_bar1, w_bar1]
    res = downsample_daily_bars(bars, today, policy)

    assert len(res) == 3

    # Check monthly aggregated bar
    monthly_bar = res[0]
    assert monthly_bar.symbol == "AAPL"
    assert monthly_bar.ts == date(2016, 11, 1)
    assert monthly_bar.open == Decimal("100")
    assert monthly_bar.high == Decimal("108")
    assert monthly_bar.low == Decimal("99")
    assert monthly_bar.close == Decimal("107")
    assert monthly_bar.volume == 5000

    # Check weekly aggregated bar (week starts Monday 2021-11-15)
    weekly_bar = res[1]
    assert weekly_bar.symbol == "AAPL"
    assert weekly_bar.ts == date(2021, 11, 15)
    assert weekly_bar.open == Decimal("140")
    assert weekly_bar.high == Decimal("148")
    assert weekly_bar.low == Decimal("138")
    assert weekly_bar.close == Decimal("146")
    assert weekly_bar.volume == 1100

    # Check recent bar (untouched)
    assert res[2] == recent_bar

    # Check idempotence: running again on res returns res
    res_second = downsample_daily_bars(res, today, policy)
    assert res_second == res


def test_downsample_hourly_boundaries_and_idempotence():
    today = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    policy = RetentionPolicy(hourly_days=90)
    # cutoff date = 2026-11-18 - 90 days = 2026-08-20

    # Recent hourly bar: 2026-08-21 10:00 UTC (> 90 days cutoff)
    recent_hour = Bar(
        symbol="MSFT",
        ts=datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
        open=Decimal("400"),
        high=Decimal("402"),
        low=Decimal("399"),
        close=Decimal("401"),
        volume=100,
    )

    # Older hourly bars: 2026-08-20 (exact cutoff date)
    old_h1 = Bar(
        symbol="MSFT",
        ts=datetime(2026, 8, 20, 9, 30, tzinfo=UTC),
        open=Decimal("390"),
        high=Decimal("395"),
        low=Decimal("389"),
        close=Decimal("392"),
        volume=200,
    )
    old_h2 = Bar(
        symbol="MSFT",
        ts=datetime(2026, 8, 20, 15, 30, tzinfo=UTC),
        open=Decimal("392"),
        high=Decimal("398"),
        low=Decimal("391"),
        close=Decimal("397"),
        volume=300,
    )

    bars = [old_h2, recent_hour, old_h1]
    res = downsample_hourly(bars, today, policy)

    assert len(res) == 2

    # Check aggregated daily bar
    daily_bar = res[0]
    assert daily_bar.symbol == "MSFT"
    assert daily_bar.ts == date(2026, 8, 20)
    assert daily_bar.open == Decimal("390")
    assert daily_bar.high == Decimal("398")
    assert daily_bar.low == Decimal("389")
    assert daily_bar.close == Decimal("397")
    assert daily_bar.volume == 500

    # Recent hour remains untouched
    assert res[1] == recent_hour

    # Idempotence
    assert downsample_hourly(res, today, policy) == res


def test_compact_news():
    today = date(2026, 11, 18)
    cutoff = today - timedelta(days=90)  # 2026-08-20

    item_old = NewsItem(
        id="news-1",
        published_at=cutoff,
        title="Old Fed Announcement",
        summary="Fed holds rates.",
        text="Full long transcript here...",
    )
    item_recent = NewsItem(
        id="news-2",
        published_at=cutoff + timedelta(days=1),
        title="Recent Earnings",
        summary="NVDA beats.",
        text="Full earnings report details...",
    )

    items = [item_old, item_recent]
    res = compact_news(items, today)

    assert len(res) == 2
    assert res[0].id == "news-1"
    assert res[0].text is None
    assert res[0].title == "Old Fed Announcement"
    assert res[0].summary == "Fed holds rates."

    assert res[1] == item_recent
    assert res[1].text == "Full earnings report details..."

    # Idempotent
    assert compact_news(res, today) == res


def test_compact_llm_records():
    today = date(2026, 11, 18)
    cutoff = today - timedelta(days=180)

    rec_old = LlmRecord(
        id="llm-1",
        created_at=cutoff,
        agent="Analyst",
        chat_id="AAPL",
        tokens=1500,
        cost=Decimal("0.015"),
        duration_ms=450,
        prompt="Analyze AAPL Q3",
        response="AAPL looks bullish",
    )
    rec_recent = LlmRecord(
        id="llm-2",
        created_at=cutoff + timedelta(days=1),
        agent="PM",
        chat_id="PORTFOLIO",
        tokens=3000,
        cost=Decimal("0.03"),
        duration_ms=900,
        prompt="Review orders",
        response="Approve order #1",
    )

    records = [rec_old, rec_recent]
    res = compact_llm_records(records, today)

    assert len(res) == 2
    assert res[0].id == "llm-1"
    assert res[0].prompt is None
    assert res[0].response is None
    assert res[0].tokens == 1500
    assert res[0].cost == Decimal("0.015")
    assert res[0].duration_ms == 450
    assert res[0].agent == "Analyst"

    assert res[1] == rec_recent
    assert res[1].prompt == "Review orders"
    assert res[1].response == "Approve order #1"

    # Idempotent
    assert compact_llm_records(res, today) == res
