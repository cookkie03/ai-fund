"""Deterministic trailing stop logic."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple

DEFAULT_K_TRAIL_ACT = Decimal("1.5")
DEFAULT_K_TRAIL = Decimal("1.0")


def _to_decimal(val: Decimal | int | float | str) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


@dataclass(frozen=True)
class TrailingState:
    """State of an active or tracking trailing stop."""

    entry: Decimal
    atr: Decimal
    k_trail_act: Decimal
    k_trail: Decimal
    active: bool
    highest: Decimal
    stop: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry", _to_decimal(self.entry))
        object.__setattr__(self, "atr", _to_decimal(self.atr))
        object.__setattr__(self, "k_trail_act", _to_decimal(self.k_trail_act))
        object.__setattr__(self, "k_trail", _to_decimal(self.k_trail))
        object.__setattr__(self, "highest", _to_decimal(self.highest))
        object.__setattr__(self, "stop", _to_decimal(self.stop))

        if self.entry <= Decimal("0"):
            raise ValueError("entry must be positive")
        if self.atr <= Decimal("0"):
            raise ValueError("atr must be positive")
        if self.k_trail_act <= Decimal("0"):
            raise ValueError("k_trail_act must be positive")
        if self.k_trail <= Decimal("0"):
            raise ValueError("k_trail must be positive")


class TrailingResult(NamedTuple):
    """Result of next_trailing_stop returning new state and whether stop changed."""

    state: TrailingState
    stop_changed: bool


def next_trailing_stop(
    state: TrailingState,
    price: Decimal | float | int | str,
    atr_at_entry: Decimal | float | int | str | None = None,
) -> TrailingResult:
    """Calculate the next trailing stop state based on the latest price observation.

    Parameters
    ----------
    state:
        The current TrailingState.
    price:
        The latest observed price.
    atr_at_entry:
        Optional update/override for ATR (defaults to state.atr).

    Returns
    -------
    TrailingResult(state, stop_changed)
    """
    current_price = _to_decimal(price)
    if current_price <= Decimal("0"):
        raise ValueError("price must be positive")

    atr = _to_decimal(atr_at_entry) if atr_at_entry is not None else state.atr
    if atr <= Decimal("0"):
        raise ValueError("atr must be positive")

    highest = max(state.highest, current_price)
    activation_threshold = state.entry + (state.k_trail_act * atr)

    active = state.active or (current_price >= activation_threshold)

    if not active:
        new_state = TrailingState(
            entry=state.entry,
            atr=atr,
            k_trail_act=state.k_trail_act,
            k_trail=state.k_trail,
            active=False,
            highest=highest,
            stop=state.stop,
        )
        return TrailingResult(state=new_state, stop_changed=False)

    # Active trailing stop:
    # Stop moves to break-even (entry) on activation, then trails highest - k_trail*atr.
    # Never lowered below current stop or below entry.
    trail_target = highest - (state.k_trail * atr)
    new_stop = max(state.stop, state.entry, trail_target)
    stop_changed = new_stop != state.stop

    new_state = TrailingState(
        entry=state.entry,
        atr=atr,
        k_trail_act=state.k_trail_act,
        k_trail=state.k_trail,
        active=True,
        highest=highest,
        stop=new_stop,
    )
    return TrailingResult(state=new_state, stop_changed=stop_changed)
