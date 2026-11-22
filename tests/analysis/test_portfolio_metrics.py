"""Formule delle metriche di portafoglio su serie note (nessuna rete, nessun DB)."""

from __future__ import annotations

import math

import pytest

from analysis.portfolio_metrics import (
    MIN_OBSERVATIONS,
    TradeStat,
    compute_performance,
    drawdown_series,
    period_start,
)

EQUITY = [100.0, 110.0, 99.0, 105.0, 120.0, 108.0]


def _points(values, start_day=1):
    return [(f"2026-03-{start_day + i:02d}T21:00:00Z", v) for i, v in enumerate(values)]


def test_drawdown_series_and_max():
    dd = drawdown_series(EQUITY)
    assert dd[0] == 0.0
    assert dd[2] == pytest.approx(-0.1)  # 99 vs picco 110
    assert dd[-1] == pytest.approx(-0.1)  # 108 vs picco 120
    assert min(dd) == pytest.approx(-0.1)


def test_return_and_drawdown_and_vol():
    perf = compute_performance(_points(EQUITY), [], min_obs=3)
    assert perf["return_fraction"] == pytest.approx(0.08)
    assert perf["max_drawdown_fraction"] == pytest.approx(-0.1)
    assert perf["current_drawdown_fraction"] == pytest.approx(-0.1)
    rets = [EQUITY[i] / EQUITY[i - 1] - 1 for i in range(1, len(EQUITY))]
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    assert perf["volatility_annualized"] == pytest.approx(sd * math.sqrt(252))
    assert perf["sharpe"] == pytest.approx(mean / sd * math.sqrt(252))
    downside = math.sqrt(sum(min(r, 0.0) ** 2 for r in rets) / len(rets))
    assert perf["sortino"] == pytest.approx(mean / downside * math.sqrt(252))
    assert all(
        i["metric"] not in ("sharpe", "sortino", "volatility_annualized")
        for i in perf["insufficient"]
    )


def test_insufficient_observations_returns_null_with_reason():
    perf = compute_performance(_points([100.0, 101.0, 102.0]), [])
    assert perf["observations"] == 3
    for metric in ("sharpe", "sortino", "volatility_annualized"):
        assert perf[metric] is None
    names = {i["metric"] for i in perf["insufficient"]}
    assert {"sharpe", "sortino", "volatility_annualized"} <= names
    assert all(i["min_observations"] == MIN_OBSERVATIONS[i["metric"]] for i in perf["insufficient"])
    # il rendimento di periodo resta calcolabile con 2+ punti
    assert perf["return_fraction"] == pytest.approx(0.02)


def test_empty_series_everything_null():
    perf = compute_performance([], [])
    assert perf["observations"] == 0
    assert perf["return_fraction"] is None
    assert perf["max_drawdown_fraction"] is None
    assert perf["benchmark"] is None


def test_trade_stats():
    trades = [
        TradeStat(pnl=300.0, r_multiple=3.0),
        TradeStat(pnl=-100.0, r_multiple=-1.0),
        TradeStat(pnl=200.0, r_multiple=2.0),
        TradeStat(pnl=-100.0, r_multiple=-1.0),
    ]
    perf = compute_performance(_points(EQUITY), trades, min_obs=3, min_trades=3)
    assert perf["trades_closed"] == 4
    assert perf["win_rate"] == pytest.approx(0.5)
    assert perf["profit_factor"] == pytest.approx(500.0 / 200.0)
    assert perf["expectancy"] == pytest.approx(75.0)
    assert perf["expectancy_r"] == pytest.approx(0.75)
    assert perf["realized_pnl"] == pytest.approx(300.0)


def test_trade_stats_insufficient_below_min_trades():
    trades = [TradeStat(pnl=10.0, r_multiple=1.0)]
    perf = compute_performance(_points(EQUITY), trades, min_obs=3)
    assert perf["win_rate"] is None and perf["profit_factor"] is None
    assert perf["expectancy"] is None
    assert perf["trades_closed"] == 1
    assert {"win_rate", "profit_factor", "expectancy"} <= {i["metric"] for i in perf["insufficient"]}


def test_profit_factor_without_losses_is_null_not_infinite():
    trades = [TradeStat(pnl=10.0, r_multiple=1.0)] * 5
    perf = compute_performance(_points(EQUITY), trades, min_obs=3, min_trades=3)
    assert perf["profit_factor"] is None
    assert perf["win_rate"] == 1.0


def test_benchmark_beta_correlation():
    bench = [100.0, 102.0, 101.0, 104.0, 110.0, 105.0]
    # portafoglio = 2x i rendimenti del benchmark -> beta 2, corr 1
    eq = [100.0]
    for i in range(1, len(bench)):
        eq.append(eq[-1] * (1 + 2 * (bench[i] / bench[i - 1] - 1)))
    pts = _points(eq)
    bpts = _points(bench)
    perf = compute_performance(pts, [], benchmark=("SPY", bpts), min_obs=3)
    b = perf["benchmark"]
    assert b["ticker"] == "SPY"
    assert b["beta"] == pytest.approx(2.0)
    assert b["correlation"] == pytest.approx(1.0)
    assert b["return_fraction"] == pytest.approx(0.05)


def test_benchmark_missing_or_too_short_is_null():
    assert compute_performance(_points(EQUITY), [], benchmark=("SPY", []), min_obs=3)[
        "benchmark"
    ] is None
    assert compute_performance(_points(EQUITY), [], benchmark=None, min_obs=3)["benchmark"] is None


def test_period_start():
    from datetime import UTC, datetime

    now = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
    assert period_start("1D", now) == datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    assert period_start("1W", now) == datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    assert period_start("1M", now) == datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    assert period_start("3M", now) == datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    assert period_start("YTD", now) == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert period_start("1Y", now) == datetime(2025, 11, 22, 12, 0, tzinfo=UTC)
    assert period_start("ALL", now) is None
    with pytest.raises(ValueError):
        period_start("5Y", now)
