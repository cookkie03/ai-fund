"""Tests for the Risk Gate ordered guards and boundary conditions."""

from datetime import date
from decimal import Decimal

from execution.risk_gate import (
    GateOrder,
    GuardResult,
    RiskGateContext,
    RiskGateLimits,
    default_trading_days_between,
    guard_cash_reserve,
    guard_earnings_date,
    guard_max_open_positions,
    guard_no_short,
    guard_position_size,
    guard_risk_per_trade,
    guard_risk_reward,
    guard_sector_exposure,
    guard_system_halt,
    run_risk_gate,
)


def make_order(**overrides) -> GateOrder:
    values = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": Decimal("10"),
        "entry": Decimal("100"),
        "stop": Decimal("95"),
        "take_profit": Decimal("110"),  # (110 - 100) / (100 - 95) = 2.0 >= 1.5
        "sector": "Technology",
    }
    values.update(overrides)
    return GateOrder(**values)


def make_context(**overrides) -> RiskGateContext:
    values = {
        "equity": Decimal("100000"),
        "cash": Decimal("50000"),
        "positions": {},
        "sector_map": {},
        "open_risk": Decimal("0"),
        "open_positions_count": 0,
        "halted": False,
        "next_earnings_date": None,
        "today": date(2026, 11, 16),  # Monday
        "trading_days_between": default_trading_days_between,
        "position_quantities": {},
        "limits": RiskGateLimits(),
    }
    values.update(overrides)
    return RiskGateContext(**values)


# ---------------------------------------------------------------------------
# Trading days calculation
# ---------------------------------------------------------------------------


def test_trading_days_between_weekdays():
    # Monday to Wednesday = 2 days (Tue, Wed)
    assert default_trading_days_between(date(2026, 11, 16), date(2026, 11, 18)) == 2
    # Friday to Monday = 1 day (Mon)
    assert default_trading_days_between(date(2026, 11, 20), date(2026, 11, 23)) == 1
    # Friday to Tuesday = 2 days (Mon, Tue)
    assert default_trading_days_between(date(2026, 11, 20), date(2026, 11, 24)) == 2
    # Same date = 0
    assert default_trading_days_between(date(2026, 11, 16), date(2026, 11, 16)) == 0


# ---------------------------------------------------------------------------
# Guard 1: System Halt
# ---------------------------------------------------------------------------


def test_guard_system_halt_blocks_buy_and_sell():
    ctx_halted = make_context(halted=True)
    buy_order = make_order(side="buy")
    sell_order = make_order(side="sell")

    res_buy = guard_system_halt(buy_order, ctx_halted)
    res_sell = guard_system_halt(sell_order, ctx_halted)

    assert not res_buy.ok
    assert "halt" in res_buy.reason.lower()
    assert not res_sell.ok
    assert "halt" in res_sell.reason.lower()


def test_guard_system_halt_allows_when_not_halted():
    ctx = make_context(halted=False)
    res = guard_system_halt(make_order(), ctx)
    assert res.ok
    assert res.reason is None


# ---------------------------------------------------------------------------
# Guard 2: No Short (Sell position check)
# ---------------------------------------------------------------------------


def test_guard_no_short_blocks_sell_without_position():
    ctx = make_context(positions={}, position_quantities={})
    sell_order = make_order(side="sell", quantity=Decimal("10"))

    res = guard_no_short(sell_order, ctx)
    assert not res.ok
    assert "short" in res.reason.lower() or "position" in res.reason.lower()


def test_guard_no_short_boundary_exact_quantity():
    # Exactly at limit: selling full position is allowed
    ctx = make_context(
        positions={"AAPL": Decimal("1000")},
        position_quantities={"AAPL": Decimal("10")},
    )
    sell_exact = make_order(side="sell", quantity=Decimal("10"))
    res = guard_no_short(sell_exact, ctx)
    assert res.ok


def test_guard_no_short_boundary_just_over_quantity():
    # Just over limit: selling 10.01 when holding 10 is blocked
    ctx = make_context(
        positions={"AAPL": Decimal("1000")},
        position_quantities={"AAPL": Decimal("10")},
    )
    sell_over = make_order(side="sell", quantity=Decimal("10.01"))
    res = guard_no_short(sell_over, ctx)
    assert not res.ok
    assert "exceeds" in res.reason.lower() or "insufficient" in res.reason.lower()


def test_guard_no_short_ignores_buy_order():
    ctx = make_context(positions={}, position_quantities={})
    buy_order = make_order(side="buy", quantity=Decimal("100"))
    res = guard_no_short(buy_order, ctx)
    assert res.ok


# ---------------------------------------------------------------------------
# Guard 3: Earnings Date
# ---------------------------------------------------------------------------


def test_guard_earnings_date_boundaries():
    # Monday Nov 16 today. Limit is 2 trading days.
    # Nov 18 (Wed) = 2 trading days -> within 2 days -> BLOCKED
    ctx_2_days = make_context(next_earnings_date=date(2026, 11, 18))
    res_blocked = guard_earnings_date(make_order(side="buy"), ctx_2_days)
    assert not res_blocked.ok
    assert "earnings" in res_blocked.reason.lower()

    # Nov 19 (Thu) = 3 trading days -> > 2 days -> ALLOWED
    ctx_3_days = make_context(next_earnings_date=date(2026, 11, 19))
    res_allowed = guard_earnings_date(make_order(side="buy"), ctx_3_days)
    assert res_allowed.ok

    # No earnings date -> ALLOWED
    ctx_no_earnings = make_context(next_earnings_date=None)
    assert guard_earnings_date(make_order(side="buy"), ctx_no_earnings).ok

    # Sell orders are not blocked by earnings
    sell_order = make_order(side="sell")
    assert guard_earnings_date(sell_order, ctx_2_days).ok


# ---------------------------------------------------------------------------
# Guard 4: Max Open Positions
# ---------------------------------------------------------------------------


def test_guard_max_open_positions_boundaries():
    # Limit is 30 open positions.
    # At 29 positions: new position allowed (reaches 30)
    ctx_29 = make_context(open_positions_count=29)
    assert guard_max_open_positions(make_order(symbol="NEW", side="buy"), ctx_29).ok

    # At 30 positions: new position blocked (would reach 31)
    ctx_30 = make_context(open_positions_count=30)
    res_30 = guard_max_open_positions(make_order(symbol="NEW", side="buy"), ctx_30)
    assert not res_30.ok
    assert "open positions" in res_30.reason.lower()

    # At 30 positions: adding to existing position AAPL is allowed
    ctx_existing = make_context(
        open_positions_count=30,
        positions={"AAPL": Decimal("5000")},
    )
    assert guard_max_open_positions(make_order(symbol="AAPL", side="buy"), ctx_existing).ok

    # Sell order is always allowed
    assert guard_max_open_positions(make_order(symbol="NEW", side="sell"), ctx_30).ok


# ---------------------------------------------------------------------------
# Guard 5: Max Risk Per Trade (<= 1% equity)
# ---------------------------------------------------------------------------


def test_guard_risk_per_trade_boundaries():
    # Equity = 10,000 -> 1% = 100 risk limit.
    ctx = make_context(equity=Decimal("10000"))

    # Entry 100, Stop 90 -> risk per share = 10.
    # Exactly at limit: quantity 10 -> risk = 100.
    order_at_limit = make_order(quantity=Decimal("10"), entry=Decimal("100"), stop=Decimal("90"))
    assert guard_risk_per_trade(order_at_limit, ctx).ok

    # Just over limit: quantity 10.01 -> risk = 100.10 > 100.
    order_over_limit = make_order(
        quantity=Decimal("10.01"), entry=Decimal("100"), stop=Decimal("90")
    )
    res = guard_risk_per_trade(order_over_limit, ctx)
    assert not res.ok
    assert "risk" in res.reason.lower()


# ---------------------------------------------------------------------------
# Guard 6: Max Position Size (<= 10% equity)
# ---------------------------------------------------------------------------


def test_guard_position_size_boundaries():
    # Equity = 10,000 -> 10% = 1,000 max position.
    ctx = make_context(equity=Decimal("10000"), positions={})

    # Exactly at limit: quantity 10 * entry 100 = 1000.
    order_at_limit = make_order(quantity=Decimal("10"), entry=Decimal("100"))
    assert guard_position_size(order_at_limit, ctx).ok

    # Just over limit: quantity 10.01 * entry 100 = 1001 > 1000.
    order_over = make_order(quantity=Decimal("10.01"), entry=Decimal("100"))
    res = guard_position_size(order_over, ctx)
    assert not res.ok
    assert "position" in res.reason.lower()

    # Cumulative with existing position: existing 400 + order 600 = 1000 (allowed)
    ctx_with_pos = make_context(equity=Decimal("10000"), positions={"AAPL": Decimal("400")})
    order_cumulative_exact = make_order(
        symbol="AAPL", quantity=Decimal("6"), entry=Decimal("100")
    )
    assert guard_position_size(order_cumulative_exact, ctx_with_pos).ok

    # Cumulative over: existing 400 + order 601 = 1001 (blocked)
    order_cumulative_over = make_order(
        symbol="AAPL", quantity=Decimal("6.01"), entry=Decimal("100")
    )
    res_cum = guard_position_size(order_cumulative_over, ctx_with_pos)
    assert not res_cum.ok


# ---------------------------------------------------------------------------
# Guard 7: Max Sector Exposure (<= 30% equity)
# ---------------------------------------------------------------------------


def test_guard_sector_exposure_boundaries():
    # Equity = 10,000 -> 30% = 3,000 max sector exposure.
    # Existing Tech = 2000 in MSFT
    ctx = make_context(
        equity=Decimal("10000"),
        positions={"MSFT": Decimal("2000")},
        sector_map={"MSFT": "Technology"},
    )

    # Exactly at limit: 2000 + 1000 = 3000
    order_exact = make_order(
        symbol="AAPL", sector="Technology", quantity=Decimal("10"), entry=Decimal("100")
    )
    assert guard_sector_exposure(order_exact, ctx).ok

    # Just over limit: 2000 + 1001 = 3001
    order_over = make_order(
        symbol="AAPL", sector="Technology", quantity=Decimal("10.01"), entry=Decimal("100")
    )
    res = guard_sector_exposure(order_over, ctx)
    assert not res.ok
    assert "sector" in res.reason.lower()


# ---------------------------------------------------------------------------
# Guard 8: Cash Reserve (>= 5% equity after order)
# ---------------------------------------------------------------------------


def test_guard_cash_reserve_boundaries():
    # Equity = 10,000 -> 5% reserve = 500.
    # Cash = 2500. Max spend = 2000.
    ctx = make_context(equity=Decimal("10000"), cash=Decimal("2500"))

    # Exactly at limit: order notional = 2000 -> cash left = 500
    order_exact = make_order(quantity=Decimal("20"), entry=Decimal("100"))
    assert guard_cash_reserve(order_exact, ctx).ok

    # Just over limit: order notional = 2001 -> cash left = 499 < 500
    order_over = make_order(quantity=Decimal("20.01"), entry=Decimal("100"))
    res = guard_cash_reserve(order_over, ctx)
    assert not res.ok
    assert "cash" in res.reason.lower()


# ---------------------------------------------------------------------------
# Guard 9: Risk/Reward Ratio (>= 1.5)
# ---------------------------------------------------------------------------


def test_guard_risk_reward_boundaries():
    # Entry 100, Stop 90 -> Risk = 10.
    # Exactly at limit: TP 115 -> Reward = 15 -> R:R = 1.5
    order_exact = make_order(entry=Decimal("100"), stop=Decimal("90"), take_profit=Decimal("115"))
    assert guard_risk_reward(order_exact, make_context()).ok

    # Just under limit: TP 114.99 -> Reward = 14.99 -> R:R = 1.499 < 1.5
    order_under = make_order(
        entry=Decimal("100"), stop=Decimal("90"), take_profit=Decimal("114.99")
    )
    res = guard_risk_reward(order_under, make_context())
    assert not res.ok
    assert "risk/reward" in res.reason.lower() or "r:r" in res.reason.lower()


# ---------------------------------------------------------------------------
# run_risk_gate: Full pipeline, multiple reasons & ordering ("stop at none")
# ---------------------------------------------------------------------------


def test_run_risk_gate_approves_clean_order():
    order = make_order(
        quantity=Decimal("5"), entry=Decimal("100"), stop=Decimal("90"), take_profit=Decimal("120")
    )
    ctx = make_context()
    result = run_risk_gate(order, ctx)

    assert result.allowed is True
    assert result.reasons == ()


def test_run_risk_gate_collects_all_reasons_without_stopping_and_preserves_order():
    # Order triggers:
    # 1. Halted
    # 2. Risk per trade (> 1%)
    # 3. Cash reserve (< 5%)
    # 4. R:R (< 1.5)
    ctx = make_context(
        equity=Decimal("10000"),
        cash=Decimal("500"),  # Reserve needed is 500, any buy breaches cash
        halted=True,
    )
    bad_order = make_order(
        quantity=Decimal("50"),  # Notional 5000, risk 50*(100-90)=500 > 100 limit
        entry=Decimal("100"),
        stop=Decimal("90"),
        take_profit=Decimal("105"),  # Reward 5 / Risk 10 = 0.5 < 1.5
    )

    result = run_risk_gate(bad_order, ctx)

    assert result.allowed is False
    assert len(result.reasons) >= 4

    # Verify order of reasons corresponds to DEFAULT_GUARDS:
    # Halt check is first
    assert "halt" in result.reasons[0].lower()
    # Risk per trade
    assert any("risk" in r.lower() and "trade" in r.lower() for r in result.reasons)
    # Cash reserve
    assert any("cash" in r.lower() for r in result.reasons)
    # R:R
    assert any("risk/reward" in r.lower() or "r:r" in r.lower() for r in result.reasons)


def test_run_risk_gate_custom_guard():
    def custom_guard(order, ctx):
        return GuardResult(ok=False, reason="Custom guard block")

    order = make_order()
    ctx = make_context()
    result = run_risk_gate(order, ctx, guards=(custom_guard,))

    assert result.allowed is False
    assert result.reasons == ("Custom guard block",)


def test_run_risk_gate_custom_guard_taking_ctx_only():
    def custom_guard_ctx(ctx):
        return GuardResult(ok=False, reason="Ctx-only guard block")

    order = make_order()
    ctx = make_context()
    result = run_risk_gate(order, ctx, guards=(custom_guard_ctx,))

    assert result.allowed is False
    assert result.reasons == ("Ctx-only guard block",)


def test_run_risk_gate_configurable_limits():
    # With custom limits: allow 2% risk per trade instead of 1%
    custom_limits = RiskGateLimits(
        max_risk_per_trade=Decimal("0.02"), max_position_size=Decimal("0.20")
    )
    ctx = make_context(equity=Decimal("10000"), limits=custom_limits)

    # Risk = 150 (1.5% of 10,000), position 1500 (15% <= 20%), R:R 2.0
    order = make_order(
        quantity=Decimal("15"), entry=Decimal("100"), stop=Decimal("90"),
        take_profit=Decimal("120"),
    )
    result = run_risk_gate(order, ctx)

    assert result.allowed is True
