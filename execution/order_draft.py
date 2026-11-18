"""Deterministic order draft (Bozza dell'ordine) calculation."""

from __future__ import annotations

import decimal
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

DEFAULT_K_STOP = Decimal("2.0")
DEFAULT_K_TP = Decimal("3.0")
DEFAULT_K_TRAIL_ACT = Decimal("1.5")
DEFAULT_K_TRAIL = Decimal("1.0")


class DraftNotViable(ValueError):
    """Raised when an order draft is not viable (e.g. calculated size is 0)."""


def _to_decimal(val: Decimal | int | float | str) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def default_k_entry(conviction: Decimal | float | int) -> Decimal:
    """Calculate default k_entry linearly decreasing with conviction in [0, 1].

    At conviction 0: k_entry = 1.0.
    At conviction 1: k_entry = 0.2.
    """
    c = _to_decimal(conviction)
    if c < Decimal("0") or c > Decimal("1"):
        raise ValueError(f"conviction must be between 0 and 1, got {conviction}")
    return Decimal("1.0") - Decimal("0.8") * c


@dataclass(frozen=True)
class OrderDraftInputs:
    """Inputs required to construct a deterministic order draft."""

    symbol: str
    side: str
    current_price: Decimal
    atr: Decimal
    equity: Decimal
    risk_fraction: Decimal
    k_entry: Decimal = Decimal("1.0")
    k_stop: Decimal = DEFAULT_K_STOP
    k_tp: Decimal = DEFAULT_K_TP
    position_quantity: Decimal | None = None

    def __post_init__(self) -> None:
        sym = self.symbol.strip().upper()
        if not sym:
            raise ValueError("symbol must not be empty")
        object.__setattr__(self, "symbol", sym)

        s = self.side.strip().lower()
        if s not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {self.side!r}. Must be 'buy' or 'sell'.")
        object.__setattr__(self, "side", s)

        price = _to_decimal(self.current_price)
        if price <= Decimal("0"):
            raise ValueError("current_price must be positive")
        object.__setattr__(self, "current_price", price)

        atr_val = _to_decimal(self.atr)
        if atr_val <= Decimal("0"):
            raise ValueError("atr must be positive")
        object.__setattr__(self, "atr", atr_val)

        eq = _to_decimal(self.equity)
        if eq <= Decimal("0"):
            raise ValueError("equity must be positive")
        object.__setattr__(self, "equity", eq)

        rf = _to_decimal(self.risk_fraction)
        if rf <= Decimal("0") or rf > Decimal("1"):
            raise ValueError("risk_fraction must be in (0, 1]")
        object.__setattr__(self, "risk_fraction", rf)

        ke = _to_decimal(self.k_entry)
        if ke < Decimal("0"):
            raise ValueError("k_entry must be non-negative")
        object.__setattr__(self, "k_entry", ke)

        ks = _to_decimal(self.k_stop)
        if ks <= Decimal("0"):
            raise ValueError("k_stop must be positive")
        object.__setattr__(self, "k_stop", ks)

        kt = _to_decimal(self.k_tp)
        if kt <= Decimal("0"):
            raise ValueError("k_tp must be positive")
        object.__setattr__(self, "k_tp", kt)

        if self.position_quantity is not None:
            pq = _to_decimal(self.position_quantity)
            if pq < Decimal("0"):
                raise ValueError("position_quantity must not be negative")
            object.__setattr__(self, "position_quantity", pq)


@dataclass(frozen=True)
class OrderDraft:
    """Deterministic order draft (Bozza dell'ordine)."""

    symbol: str
    side: str
    entry: Decimal
    stop: Decimal | None
    take_profit: Decimal | None
    quantity: Decimal
    risk_reward: Decimal | None
    risk_amount: Decimal | None
    notional: Decimal

    @property
    def limit_price(self) -> Decimal:
        """Alias for entry limit price."""
        return self.entry

    @property
    def draft_hash(self) -> str:
        """Deterministic sha256 content hash over canonical fields."""
        canonical_payload = {
            "entry": str(self.entry),
            "notional": str(self.notional),
            "quantity": str(self.quantity),
            "risk_amount": str(self.risk_amount) if self.risk_amount is not None else None,
            "risk_reward": str(self.risk_reward) if self.risk_reward is not None else None,
            "side": self.side,
            "stop": str(self.stop) if self.stop is not None else None,
            "symbol": self.symbol,
            "take_profit": str(self.take_profit) if self.take_profit is not None else None,
        }
        encoded = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()


def build_order_draft(inputs: OrderDraftInputs) -> OrderDraft:
    """Construct a deterministic OrderDraft from inputs."""
    if inputs.side == "buy":
        entry = inputs.current_price - (inputs.k_entry * inputs.atr)
        if entry <= Decimal("0"):
            raise DraftNotViable(f"Calculated entry price must be positive, got {entry}")

        stop = entry - (inputs.k_stop * inputs.atr)
        if stop <= Decimal("0"):
            raise DraftNotViable(f"Calculated stop price must be positive, got {stop}")

        take_profit = entry + (inputs.k_tp * inputs.atr)

        risk_per_share = entry - stop
        risk_budget = inputs.equity * inputs.risk_fraction
        raw_size = risk_budget / risk_per_share
        size_int = int(raw_size.to_integral_value(rounding=decimal.ROUND_FLOOR))

        if size_int <= 0:
            raise DraftNotViable(
                f"Order draft not viable: calculated size is {size_int} (budget={risk_budget})"
            )

        quantity = Decimal(size_int)
        risk_amount = quantity * risk_per_share
        risk_reward = (take_profit - entry) / risk_per_share
        notional = quantity * entry

        return OrderDraft(
            symbol=inputs.symbol,
            side="buy",
            entry=entry,
            stop=stop,
            take_profit=take_profit,
            quantity=quantity,
            risk_reward=risk_reward,
            risk_amount=risk_amount,
            notional=notional,
        )

    if inputs.side == "sell":
        if inputs.position_quantity is None or inputs.position_quantity <= Decimal("0"):
            raise ValueError("Cannot build sell order draft without an open position quantity")

        entry = inputs.current_price + (inputs.k_entry * inputs.atr)
        quantity = inputs.position_quantity
        notional = quantity * entry

        return OrderDraft(
            symbol=inputs.symbol,
            side="sell",
            entry=entry,
            stop=None,
            take_profit=None,
            quantity=quantity,
            risk_reward=None,
            risk_amount=None,
            notional=notional,
        )

    raise ValueError(f"Unsupported side: {inputs.side!r}")
