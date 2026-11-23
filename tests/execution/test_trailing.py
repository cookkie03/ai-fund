"""Unit tests for deterministic trailing stop logic."""

from decimal import Decimal

import pytest

from execution.trailing import (
    DEFAULT_K_TRAIL,
    DEFAULT_K_TRAIL_ACT,
    TrailingResult,
    TrailingState,
    next_trailing_stop,
)


def test_trailing_state_initialization() -> None:
    state = TrailingState(
        entry=Decimal("100"),
        atr=Decimal("2"),
        k_trail_act=DEFAULT_K_TRAIL_ACT,
        k_trail=DEFAULT_K_TRAIL,
        active=False,
        highest=Decimal("100"),
        stop=Decimal("96"),
    )
    assert state.entry == Decimal("100")
    assert state.atr == Decimal("2")
    assert state.k_trail_act == Decimal("1.5")
    assert state.k_trail == Decimal("1.0")
    assert not state.active
    assert state.highest == Decimal("100")
    assert state.stop == Decimal("96")


def test_trailing_stop_inactive_below_threshold() -> None:
    # entry 100, atr 2, k_trail_act 1.5 -> activation threshold = 100 + 1.5*2 = 103
    state = TrailingState(
        entry=Decimal("100"),
        atr=Decimal("2"),
        k_trail_act=Decimal("1.5"),
        k_trail=Decimal("1.0"),
        active=False,
        highest=Decimal("100"),
        stop=Decimal("96"),
    )

    # Price moves to 102 (below 103)
    res = next_trailing_stop(state, price=Decimal("102"))
    assert isinstance(res, TrailingResult)
    new_state, changed = res
    assert not new_state.active
    assert new_state.highest == Decimal("102")
    assert new_state.stop == Decimal("96")
    assert not changed

    # Price drops to 98
    res2 = next_trailing_stop(new_state, price=Decimal("98"))
    assert not res2.state.active
    assert res2.state.highest == Decimal("102")
    assert res2.state.stop == Decimal("96")
    assert not res2.stop_changed


def test_trailing_stop_activates_at_threshold() -> None:
    # activation at 103
    state = TrailingState(
        entry=Decimal("100"),
        atr=Decimal("2"),
        k_trail_act=Decimal("1.5"),
        k_trail=Decimal("1.0"),
        active=False,
        highest=Decimal("101"),
        stop=Decimal("96"),
    )

    # Price hits exactly 103
    # Break-even = 100
    # trail_stop = highest - k_trail*atr = 103 - 1*2 = 101
    # stop = max(entry, trail_stop) = max(100, 101) = 101
    res = next_trailing_stop(state, price=Decimal("103"))
    assert res.state.active
    assert res.state.highest == Decimal("103")
    assert res.state.stop == Decimal("101")
    assert res.stop_changed


def test_trailing_stop_break_even_floor() -> None:
    # When k_trail is large, highest - k_trail*atr might be below entry
    # e.g., k_trail = 3.0: at price 103, 103 - 3*2 = 97 (< 100)
    # Stop should move to break-even (100)
    state = TrailingState(
        entry=Decimal("100"),
        atr=Decimal("2"),
        k_trail_act=Decimal("1.5"),
        k_trail=Decimal("3.0"),
        active=False,
        highest=Decimal("100"),
        stop=Decimal("96"),
    )

    res = next_trailing_stop(state, price=Decimal("103"))
    assert res.state.active
    assert res.state.stop == Decimal("100")  # Break-even floor
    assert res.stop_changed


def test_trailing_stop_trails_higher_prices() -> None:
    state = TrailingState(
        entry=Decimal("100"),
        atr=Decimal("2"),
        k_trail_act=Decimal("1.5"),
        k_trail=Decimal("1.0"),
        active=True,
        highest=Decimal("103"),
        stop=Decimal("101"),
    )

    # Price jumps to 106
    # highest becomes 106
    # trail_stop = 106 - 1*2 = 104
    res = next_trailing_stop(state, price=Decimal("106"))
    assert res.state.active
    assert res.state.highest == Decimal("106")
    assert res.state.stop == Decimal("104")
    assert res.stop_changed


def test_trailing_stop_never_lowers() -> None:
    state = TrailingState(
        entry=Decimal("100"),
        atr=Decimal("2"),
        k_trail_act=Decimal("1.5"),
        k_trail=Decimal("1.0"),
        active=True,
        highest=Decimal("106"),
        stop=Decimal("104"),
    )

    # Price pulls back to 103
    res = next_trailing_stop(state, price=Decimal("103"))
    assert res.state.active
    assert res.state.highest == Decimal("106")
    assert res.state.stop == Decimal("104")
    assert not res.stop_changed


def test_trailing_stop_with_atr_at_entry_override() -> None:
    state = TrailingState(
        entry=Decimal("100"),
        atr=Decimal("2"),
        k_trail_act=Decimal("1.5"),
        k_trail=Decimal("1.0"),
        active=True,
        highest=Decimal("106"),
        stop=Decimal("104"),
    )

    # Provide new atr_at_entry = 1.5
    # highest = 108 -> trail_stop = 108 - 1.0*1.5 = 106.5
    res = next_trailing_stop(state, price=Decimal("108"), atr_at_entry=Decimal("1.5"))
    assert res.state.atr == Decimal("1.5")
    assert res.state.highest == Decimal("108")
    assert res.state.stop == Decimal("106.5")
    assert res.stop_changed


def test_trailing_invalid_inputs() -> None:
    state = TrailingState(
        entry=Decimal("100"),
        atr=Decimal("2"),
        k_trail_act=Decimal("1.5"),
        k_trail=Decimal("1.0"),
        active=False,
        highest=Decimal("100"),
        stop=Decimal("96"),
    )

    with pytest.raises(ValueError, match="price"):
        next_trailing_stop(state, price=Decimal("0"))

    with pytest.raises(ValueError, match="atr"):
        next_trailing_stop(state, price=Decimal("101"), atr_at_entry=Decimal("-1"))
