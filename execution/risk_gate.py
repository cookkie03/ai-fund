"""Deterministic Risk Gate ordered guards for order validation."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal


def default_trading_days_between(start: date, end: date) -> int:
    """Calculate the number of trading days (weekdays) strictly between start and end.

    Count weekdays d where start < d <= end.
    If end <= start, returns 0.
    """
    if end <= start:
        return 0
    trading_days = 0
    current = start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:  # Monday to Friday
            trading_days += 1
        current += timedelta(days=1)
    return trading_days


@dataclass(frozen=True)
class GateOrder:
    symbol: str
    side: Literal["buy", "sell"]
    quantity: Decimal
    entry: Decimal
    stop: Decimal
    take_profit: Decimal
    sector: str

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.side not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
        if self.quantity <= 0 or self.entry <= 0:
            raise ValueError("quantity and entry must be positive")
        if self.stop <= 0:
            raise ValueError("stop must be positive")
        if self.take_profit <= 0:
            raise ValueError("take_profit must be positive")

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.entry

    @property
    def risk_per_share(self) -> Decimal:
        if self.side == "buy":
            return self.entry - self.stop
        return self.stop - self.entry

    @property
    def risk(self) -> Decimal:
        return self.quantity * self.risk_per_share


@dataclass(frozen=True)
class RiskGateLimits:
    max_risk_per_trade: Decimal = Decimal("0.01")  # 1% equity
    max_position_size: Decimal = Decimal("0.10")  # 10% equity
    max_sector_exposure: Decimal = Decimal("0.30")  # 30% equity
    max_open_positions: int = 30
    min_cash_reserve: Decimal = Decimal("0.05")  # 5% equity
    min_risk_reward: Decimal = Decimal("1.5")
    earnings_blackout_trading_days: int = 2


@dataclass(frozen=True)
class RiskGateContext:
    equity: Decimal
    cash: Decimal
    positions: dict[str, Decimal] = field(default_factory=dict)  # symbol -> market value
    sector_map: dict[str, str] = field(default_factory=dict)  # symbol -> sector
    open_risk: Decimal = Decimal("0")
    open_positions_count: int = 0
    halted: bool = False
    next_earnings_date: date | None = None
    today: date = field(default_factory=date.today)
    trading_days_between: Callable[[date, date], int] = default_trading_days_between
    position_quantities: dict[str, Decimal] = field(default_factory=dict)  # symbol -> quantity
    limits: RiskGateLimits = field(default_factory=RiskGateLimits)

    def __post_init__(self) -> None:
        if self.equity <= 0:
            raise ValueError("equity must be positive")


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    reason: str | None = None


@dataclass(frozen=True)
class RiskGateResult:
    allowed: bool
    reasons: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Individual Pure Guards
# ---------------------------------------------------------------------------


def guard_system_halt(order: GateOrder, ctx: RiskGateContext) -> GuardResult:
    """Check halt FIRST: halted system blocks everything, buy or sell."""
    if ctx.halted:
        return GuardResult(ok=False, reason="System is halted: all order submissions blocked")
    return GuardResult(ok=True)


def guard_no_short(order: GateOrder, ctx: RiskGateContext) -> GuardResult:
    """No short: a sell is allowed only if an open position exists with sufficient quantity."""
    if order.side == "sell":
        held_quantity = ctx.position_quantities.get(order.symbol, Decimal("0"))
        if held_quantity <= 0:
            return GuardResult(
                ok=False,
                reason=f"No short allowed: no open position for symbol {order.symbol}",
            )
        if order.quantity > held_quantity:
            return GuardResult(
                ok=False,
                reason=(
                    f"Sell quantity {order.quantity} exceeds held position {held_quantity} "
                    f"for symbol {order.symbol}"
                ),
            )
    return GuardResult(ok=True)


def guard_earnings_date(order: GateOrder, ctx: RiskGateContext) -> GuardResult:
    """No new entry within earnings_blackout_trading_days (default 2) of an earnings date."""
    if order.side == "buy" and ctx.next_earnings_date is not None:
        days = ctx.trading_days_between(ctx.today, ctx.next_earnings_date)
        if 0 <= days <= ctx.limits.earnings_blackout_trading_days:
            return GuardResult(
                ok=False,
                reason=(
                    f"Entry blocked: earnings date {ctx.next_earnings_date} is within "
                    f"{days} trading days (limit: <= {ctx.limits.earnings_blackout_trading_days})"
                ),
            )
    return GuardResult(ok=True)


def guard_max_open_positions(order: GateOrder, ctx: RiskGateContext) -> GuardResult:
    """Max open positions (default 30). Adding to existing position does not increase count."""
    if order.side == "buy":
        is_new_position = (
            order.symbol not in ctx.positions and order.symbol not in ctx.position_quantities
        )
        if is_new_position and ctx.open_positions_count >= ctx.limits.max_open_positions:
            return GuardResult(
                ok=False,
                reason=(
                    f"Max open positions reached ({ctx.open_positions_count} >= "
                    f"{ctx.limits.max_open_positions})"
                ),
            )
    return GuardResult(ok=True)


def guard_risk_per_trade(order: GateOrder, ctx: RiskGateContext) -> GuardResult:
    """Max risk per trade <= 1% equity."""
    if order.side == "buy":
        max_allowed_risk = ctx.equity * ctx.limits.max_risk_per_trade
        order_risk = order.risk
        if order_risk > max_allowed_risk:
            return GuardResult(
                ok=False,
                reason=(
                    f"Risk per trade {order_risk} exceeds maximum allowed "
                    f"{max_allowed_risk} (1% equity)"
                ),
            )
    return GuardResult(ok=True)


def guard_position_size(order: GateOrder, ctx: RiskGateContext) -> GuardResult:
    """Max position <= 10% equity (cumulative with existing position value)."""
    if order.side == "buy":
        existing_val = ctx.positions.get(order.symbol, Decimal("0"))
        new_total_val = existing_val + order.notional
        max_allowed_position = ctx.equity * ctx.limits.max_position_size
        if new_total_val > max_allowed_position:
            return GuardResult(
                ok=False,
                reason=(
                    f"Position value {new_total_val} for {order.symbol} exceeds "
                    f"maximum allowed {max_allowed_position} (10% equity)"
                ),
            )
    return GuardResult(ok=True)


def guard_sector_exposure(order: GateOrder, ctx: RiskGateContext) -> GuardResult:
    """Max sector exposure <= 30% equity."""
    if order.side == "buy" and order.sector:
        existing_sector_val = sum(
            val
            for sym, val in ctx.positions.items()
            if ctx.sector_map.get(sym, "") == order.sector
        )
        new_sector_total = existing_sector_val + order.notional
        max_allowed_sector = ctx.equity * ctx.limits.max_sector_exposure
        if new_sector_total > max_allowed_sector:
            return GuardResult(
                ok=False,
                reason=(
                    f"Sector exposure for '{order.sector}' would reach {new_sector_total}, "
                    f"exceeding maximum allowed {max_allowed_sector} (30% equity)"
                ),
            )
    return GuardResult(ok=True)


def guard_cash_reserve(order: GateOrder, ctx: RiskGateContext) -> GuardResult:
    """Cash reserve >= 5% of equity after order execution."""
    if order.side == "buy":
        required_reserve = ctx.equity * ctx.limits.min_cash_reserve
        cash_after = ctx.cash - order.notional
        if cash_after < required_reserve:
            return GuardResult(
                ok=False,
                reason=(
                    f"Cash after order ({cash_after}) falls below required cash reserve "
                    f"{required_reserve} (5% equity)"
                ),
            )
    return GuardResult(ok=True)


def guard_risk_reward(order: GateOrder, ctx: RiskGateContext) -> GuardResult:
    """Min Risk/Reward ratio >= 1.5."""
    if order.side == "buy":
        risk_per_share = order.entry - order.stop
        if risk_per_share <= 0:
            return GuardResult(
                ok=False,
                reason=f"Invalid stop: stop {order.stop} must be strictly below entry {order.entry}",
            )
        reward_per_share = order.take_profit - order.entry
        if reward_per_share <= 0:
            return GuardResult(
                ok=False,
                reason=(
                    f"Invalid take_profit: take_profit {order.take_profit} "
                    f"must be strictly above entry {order.entry}"
                ),
            )
        rr_ratio = reward_per_share / risk_per_share
        if rr_ratio < ctx.limits.min_risk_reward:
            return GuardResult(
                ok=False,
                reason=(
                    f"Risk/Reward ratio {rr_ratio:.2f} is below minimum "
                    f"{ctx.limits.min_risk_reward}"
                ),
            )
    return GuardResult(ok=True)


GuardCallable = Callable[..., GuardResult]

DEFAULT_GUARDS: tuple[GuardCallable, ...] = (
    guard_system_halt,
    guard_no_short,
    guard_earnings_date,
    guard_max_open_positions,
    guard_risk_per_trade,
    guard_position_size,
    guard_sector_exposure,
    guard_cash_reserve,
    guard_risk_reward,
)


def _invoke_guard(guard: GuardCallable, order: GateOrder, ctx: RiskGateContext) -> GuardResult:
    """Support both (order, ctx) and (ctx) pure callable guards."""
    try:
        sig = inspect.signature(guard)
        params_count = len(sig.parameters)
        if params_count == 1:
            return guard(ctx)  # type: ignore
        return guard(order, ctx)
    except (ValueError, TypeError):
        return guard(order, ctx)


def run_risk_gate(
    order: GateOrder,
    ctx: RiskGateContext,
    guards: tuple[GuardCallable, ...] = DEFAULT_GUARDS,
) -> RiskGateResult:
    """Evaluate guards in order, collect all blocking reasons (stop at none).

    Can ONLY block, never modify or approve.
    """
    reasons: list[str] = []
    for guard in guards:
        res = _invoke_guard(guard, order, ctx)
        if not res.ok:
            reason = res.reason or guard.__name__
            reasons.append(reason)

    return RiskGateResult(
        allowed=len(reasons) == 0,
        reasons=tuple(reasons),
    )
