"""Metriche di performance del portafoglio: funzioni pure, nessun I/O.

Le formule sono documentate in `docs/dashboard.md` (sezione Portafoglio). Una metrica con dati
insufficienti vale `None` ed è elencata in `insufficient`: mai un numero calcolato su 3 punti.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

TRADING_DAYS_PER_YEAR = 252

# Soglie minime: osservazioni (punti equity giornalieri) o trade chiusi, secondo la metrica.
MIN_OBSERVATIONS: dict[str, int] = {
    "volatility_annualized": 10,
    "sharpe": 20,
    "sortino": 20,
    "beta": 20,
    "correlation": 20,
    "win_rate": 5,
    "profit_factor": 5,
    "expectancy": 5,
    "expectancy_r": 5,
}

PERIODS = ("1D", "1W", "1M", "3M", "YTD", "1Y", "ALL")


@dataclass(frozen=True)
class TradeStat:
    """Esito di un trade chiuso: PnL in valuta e multiplo di R (None se il rischio è ignoto)."""

    pnl: float
    r_multiple: float | None = None


def period_start(period: str, now: datetime) -> datetime | None:
    """Inizio della finestra per `period`; `None` per ALL. Solleva ValueError se sconosciuto."""
    p = period.upper()
    if p == "ALL":
        return None
    if p == "1D":
        return now - timedelta(days=1)
    if p == "1W":
        return now - timedelta(days=7)
    if p == "1M":
        return _minus_months(now, 1)
    if p == "3M":
        return _minus_months(now, 3)
    if p == "1Y":
        try:
            return now.replace(year=now.year - 1)
        except ValueError:  # 29 febbraio
            return now.replace(year=now.year - 1, day=28)
    if p == "YTD":
        return datetime(now.year, 1, 1, tzinfo=now.tzinfo or UTC)
    raise ValueError(f"Periodo sconosciuto: {period!r}. Ammessi: {', '.join(PERIODS)}")


def _minus_months(now: datetime, months: int) -> datetime:
    idx = now.year * 12 + (now.month - 1) - months
    year, month = divmod(idx, 12)
    day = now.day
    while True:
        try:
            return now.replace(year=year, month=month + 1, day=day)
        except ValueError:
            day -= 1


def drawdown_series(values: Sequence[float]) -> list[float]:
    """Drawdown per punto: valore / massimo precedente - 1 (<= 0)."""
    out: list[float] = []
    peak = -math.inf
    for v in values:
        peak = max(peak, v)
        out.append(v / peak - 1.0 if peak > 0 else 0.0)
    return out


def _daily(points: Sequence[tuple[str, float]]) -> list[tuple[str, float]]:
    """Ultimo punto di ogni giorno (YYYY-MM-DD), in ordine cronologico."""
    by_day: dict[str, float] = {}
    for ts, v in sorted(points, key=lambda p: p[0]):
        by_day[ts[:10]] = v
    return sorted(by_day.items())


def _returns(values: Sequence[float]) -> list[float]:
    return [values[i] / values[i - 1] - 1.0 for i in range(1, len(values)) if values[i - 1] != 0]


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _stdev(xs: Sequence[float]) -> float:
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _benchmark(
    ticker: str,
    bench_points: Sequence[tuple[str, float]],
    daily_equity: list[tuple[str, float]],
    min_obs: int | None,
) -> dict[str, Any] | None:
    bench = dict(_daily(bench_points))
    if len(bench) < 2 or len(daily_equity) < 2:
        return None
    aligned = [(d, v, bench[d]) for d, v in daily_equity if d in bench]
    if len(aligned) < 2:
        return None
    eq_vals = [a[1] for a in aligned]
    b_vals = [a[2] for a in aligned]
    pr, br = _returns(eq_vals), _returns(b_vals)
    n = min(len(pr), len(br))
    beta = corr = None
    threshold = min_obs if min_obs is not None else MIN_OBSERVATIONS["beta"]
    if n >= max(threshold, 2):
        mp, mb = _mean(pr[:n]), _mean(br[:n])
        cov = sum((pr[i] - mp) * (br[i] - mb) for i in range(n)) / (n - 1)
        vb = sum((br[i] - mb) ** 2 for i in range(n)) / (n - 1)
        vp = sum((pr[i] - mp) ** 2 for i in range(n)) / (n - 1)
        if vb > 0:
            beta = cov / vb
        if vb > 0 and vp > 0:
            corr = cov / math.sqrt(vb * vp)
    return {
        "ticker": ticker,
        "return_fraction": b_vals[-1] / b_vals[0] - 1.0 if b_vals[0] else None,
        "beta": beta,
        "correlation": corr,
    }


def compute_performance(
    equity_points: Sequence[tuple[str, float]],
    trades: Sequence[TradeStat],
    *,
    benchmark: tuple[str, Sequence[tuple[str, float]]] | None = None,
    min_obs: int | None = None,
    min_trades: int | None = None,
) -> dict[str, Any]:
    """Calcola le metriche per la finestra già filtrata `equity_points` (ts ISO, equity).

    `min_obs`/`min_trades` sostituiscono le soglie di default (solo per test e tuning).
    Il tasso risk-free è 0.
    """
    daily = _daily(equity_points)
    values = [v for _, v in daily]
    n = len(values)
    insufficient: list[dict[str, Any]] = []

    def need(metric: str, have: int, override: int | None) -> bool:
        threshold = override if override is not None else MIN_OBSERVATIONS[metric]
        if have >= threshold:
            return True
        insufficient.append(
            {
                "metric": metric,
                "reason": f"servono almeno {threshold} "
                + ("trade chiusi" if metric in _TRADE_METRICS else "osservazioni giornaliere")
                + f", disponibili {have}",
                "min_observations": MIN_OBSERVATIONS[metric],
            }
        )
        return False

    ret = max_dd = cur_dd = None
    if n >= 2 and values[0] != 0:
        ret = values[-1] / values[0] - 1.0
    if n >= 1:
        dd = drawdown_series(values)
        max_dd, cur_dd = min(dd), dd[-1]

    rets = _returns(values)
    vol = sharpe = sortino = None
    if need("volatility_annualized", n, min_obs) and len(rets) >= 2:
        sd = _stdev(rets)
        vol = sd * math.sqrt(TRADING_DAYS_PER_YEAR)
    if need("sharpe", n, min_obs) and len(rets) >= 2:
        sd = _stdev(rets)
        if sd > 0:
            sharpe = _mean(rets) / sd * math.sqrt(TRADING_DAYS_PER_YEAR)
    if need("sortino", n, min_obs) and len(rets) >= 2:
        downside = math.sqrt(sum(min(r, 0.0) ** 2 for r in rets) / len(rets))
        if downside > 0:
            sortino = _mean(rets) / downside * math.sqrt(TRADING_DAYS_PER_YEAR)

    pnls = [t.pnl for t in trades]
    rs = [t.r_multiple for t in trades if t.r_multiple is not None]
    count = len(trades)
    win_rate = profit_factor = expectancy = expectancy_r = None
    if need("win_rate", count, min_trades):
        win_rate = sum(1 for p in pnls if p > 0) / count
    if need("profit_factor", count, min_trades):
        gains = sum(p for p in pnls if p > 0)
        losses = -sum(p for p in pnls if p < 0)
        profit_factor = gains / losses if losses > 0 else None
    if need("expectancy", count, min_trades):
        expectancy = _mean(pnls)
    if need("expectancy_r", len(rs), min_trades) and rs:
        expectancy_r = _mean(rs)

    bench = None
    if benchmark is not None:
        bench = _benchmark(benchmark[0], benchmark[1], daily, min_obs)

    return {
        "observations": n,
        "return_fraction": ret,
        "realized_pnl": sum(pnls),
        "max_drawdown_fraction": max_dd,
        "current_drawdown_fraction": cur_dd,
        "volatility_annualized": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "expectancy_r": expectancy_r,
        "trades_closed": count,
        "benchmark": bench,
        "insufficient": insufficient,
    }


_TRADE_METRICS = {"win_rate", "profit_factor", "expectancy", "expectancy_r"}
