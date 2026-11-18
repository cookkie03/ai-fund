"""Pure retention and downsampling functions (spec 'Conservazione', US 96-98).

Implements pure transformations on immutable dataclasses:
- downsample_daily_bars: Keep daily OHLCV for 5 years; 5 to 10 years aggregate to weekly
  (open=first, high=max, low=min, close=last, volume=sum, date=Monday of week);
  older than 10 years aggregate monthly (date=1st of month).
- downsample_hourly: Hourly bars older than 90 days aggregated to daily bars (date of day).
- compact_news: News older than 90 days keep title & summary, full text set to None.
- compact_llm_records: Records older than 180 days set prompt & response to None.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class Bar:
    symbol: str
    ts: datetime | date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | int


@dataclass(frozen=True)
class NewsItem:
    id: str
    published_at: datetime | date
    title: str
    summary: str
    text: str | None


@dataclass(frozen=True)
class LlmRecord:
    id: str
    created_at: datetime | date
    agent: str
    chat_id: str
    tokens: int
    cost: Decimal
    duration_ms: int
    prompt: str | None
    response: str | None


@dataclass(frozen=True)
class RetentionPolicy:
    daily_years: int = 5
    weekly_years: int = 10
    hourly_days: int = 90
    news_full_text_days: int = 90
    llm_content_days: int = 180


def _to_date(val: datetime | date) -> date:
    if isinstance(val, datetime):
        return val.date()
    return val


def _subtract_years(d: date, years: int) -> date:
    """Subtract `years` preserving month and day (adjusting Feb 29 for leap years)."""
    target_year = d.year - years
    try:
        return d.replace(year=target_year)
    except ValueError:
        # e.g., Feb 29 in leap year -> Feb 28 in non-leap year
        return d.replace(year=target_year, day=28)


def _aggregate_bars(bars: list[Bar], group_ts: date | datetime) -> Bar:
    """Aggregate a non-empty sequence of bars into a single bar."""
    first = bars[0]
    last = bars[-1]
    high = max(b.high for b in bars)
    low = min(b.low for b in bars)
    vol = sum(b.volume for b in bars)
    return Bar(
        symbol=first.symbol,
        ts=group_ts,
        open=first.open,
        high=high,
        low=low,
        close=last.close,
        volume=vol,
    )


def downsample_daily_bars(
    bars: Sequence[Bar],
    today: date | datetime,
    policy: RetentionPolicy = RetentionPolicy(),
) -> list[Bar]:
    """Downsample daily bars according to retention policy.

    - Recent (< 5 years from today): kept as daily bars.
    - Medium (>= 5 years and < 10 years): aggregated to weekly bars (ts = Monday).
    - Old (>= 10 years): aggregated to monthly bars (ts = 1st of month).
    Idempotent: applying multiple times preserves already downsampled bars.
    """
    ref_date = _to_date(today)
    cutoff_daily = _subtract_years(ref_date, policy.daily_years)
    cutoff_weekly = _subtract_years(ref_date, policy.weekly_years)

    # Sort input bars by symbol and timestamp
    # Note: ts might be date or datetime
    sorted_bars = sorted(bars, key=lambda b: (b.symbol, _to_date(b.ts), b.ts))

    # Group by symbol
    by_symbol: dict[str, list[Bar]] = {}
    for bar in sorted_bars:
        by_symbol.setdefault(bar.symbol, []).append(bar)

    result: list[Bar] = []

    for sym, sym_bars in by_symbol.items():
        monthly_buckets: dict[tuple[int, int], list[Bar]] = {}
        weekly_buckets: dict[date, list[Bar]] = {}
        kept_bars: list[Bar] = []

        for b in sym_bars:
            d = _to_date(b.ts)
            if d <= cutoff_weekly:
                # Older than or equal to 10 years -> Monthly bucket
                key = (d.year, d.month)
                monthly_buckets.setdefault(key, []).append(b)
            elif d <= cutoff_daily:
                # Between 5 and 10 years -> Weekly bucket (Monday start)
                monday = d - timedelta(days=d.weekday())
                weekly_buckets.setdefault(monday, []).append(b)
            else:
                # Kept daily
                kept_bars.append(b)

        # Aggregate monthly buckets
        for (y, m), b_list in monthly_buckets.items():
            first_of_month = date(y, m, 1)
            result.append(_aggregate_bars(b_list, first_of_month))

        # Aggregate weekly buckets
        for monday, b_list in weekly_buckets.items():
            result.append(_aggregate_bars(b_list, monday))

        # Add kept daily bars
        result.extend(kept_bars)

    # Sort final result
    result.sort(key=lambda b: (b.symbol, _to_date(b.ts), b.ts))
    return result


def downsample_hourly(
    bars: Sequence[Bar],
    today: date | datetime,
    policy: RetentionPolicy = RetentionPolicy(),
) -> list[Bar]:
    """Downsample hourly bars older than policy.hourly_days to daily bars.

    - Recent (< 90 days from today): kept untouched.
    - Older (>= 90 days from today): aggregated to daily bars (ts = date).
    Idempotent.
    """
    ref_date = _to_date(today)
    cutoff = ref_date - timedelta(days=policy.hourly_days)

    sorted_bars = sorted(bars, key=lambda b: (b.symbol, _to_date(b.ts), b.ts))
    by_symbol: dict[str, list[Bar]] = {}
    for bar in sorted_bars:
        by_symbol.setdefault(bar.symbol, []).append(bar)

    result: list[Bar] = []
    for sym, sym_bars in by_symbol.items():
        daily_buckets: dict[date, list[Bar]] = {}
        kept_bars: list[Bar] = []

        for b in sym_bars:
            d = _to_date(b.ts)
            if d <= cutoff:
                daily_buckets.setdefault(d, []).append(b)
            else:
                kept_bars.append(b)

        for d, b_list in daily_buckets.items():
            result.append(_aggregate_bars(b_list, d))

        result.extend(kept_bars)

    result.sort(key=lambda b: (b.symbol, _to_date(b.ts), b.ts))
    return result


def compact_news(
    items: Sequence[NewsItem],
    today: date | datetime,
    policy: RetentionPolicy = RetentionPolicy(),
) -> list[NewsItem]:
    """Drop full text (set to None) for news items older than cutoff days."""
    ref_date = _to_date(today)
    cutoff = ref_date - timedelta(days=policy.news_full_text_days)

    result: list[NewsItem] = []
    for item in items:
        d = _to_date(item.published_at)
        if d <= cutoff:
            if item.text is not None:
                result.append(replace(item, text=None))
            else:
                result.append(item)
        else:
            result.append(item)
    return result


def compact_llm_records(
    records: Sequence[LlmRecord],
    today: date | datetime,
    policy: RetentionPolicy = RetentionPolicy(),
) -> list[LlmRecord]:
    """Drop prompt and response (set to None) for records older than cutoff days."""
    ref_date = _to_date(today)
    cutoff = ref_date - timedelta(days=policy.llm_content_days)

    result: list[LlmRecord] = []
    for r in records:
        d = _to_date(r.created_at)
        if d <= cutoff:
            if r.prompt is not None or r.response is not None:
                result.append(replace(r, prompt=None, response=None))
            else:
                result.append(r)
        else:
            result.append(r)
    return result
