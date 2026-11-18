"""Unit tests for deterministic order draft calculation."""

from decimal import Decimal

import pytest

from execution.order_draft import (
    DEFAULT_K_STOP,
    DEFAULT_K_TP,
    DraftNotViable,
    OrderDraft,
    OrderDraftInputs,
    build_order_draft,
    default_k_entry,
)


def test_default_k_entry_linear_conviction() -> None:
    # Linear from 1.0 at conviction 0 to 0.2 at conviction 1
    assert default_k_entry(0) == Decimal("1.0")
    assert default_k_entry(1) == Decimal("0.2")
    assert default_k_entry(Decimal("0.5")) == Decimal("0.6")
    assert default_k_entry(0.25) == Decimal("0.8")


def test_default_k_entry_out_of_bounds() -> None:
    with pytest.raises(ValueError, match="conviction"):
        default_k_entry(-0.1)
    with pytest.raises(ValueError, match="conviction"):
        default_k_entry(1.05)


def test_build_order_draft_buy_basic() -> None:
    inputs = OrderDraftInputs(
        symbol="AAPL",
        side="buy",
        current_price=Decimal("100"),
        atr=Decimal("2"),
        equity=Decimal("50000"),
        risk_fraction=Decimal("0.01"),  # 500 risk budget
        k_entry=Decimal("0.5"),  # entry = 100 - 0.5*2 = 99
        k_stop=Decimal("2.0"),  # SL = 99 - 2.0*2 = 95
        k_tp=Decimal("3.0"),  # TP = 99 + 3.0*2 = 105
    )
    draft = build_order_draft(inputs)

    assert isinstance(draft, OrderDraft)
    assert draft.symbol == "AAPL"
    assert draft.side == "buy"
    assert draft.entry == Decimal("99")
    assert draft.limit_price == Decimal("99")
    assert draft.stop == Decimal("95")
    assert draft.take_profit == Decimal("105")
    # risk_per_share = 99 - 95 = 4
    # size = floor(500 / 4) = 125
    assert draft.quantity == Decimal("125")
    assert draft.risk_amount == Decimal("500")  # 125 * 4
    assert draft.risk_reward == Decimal("1.5")  # (105-99)/(99-95) = 6/4 = 1.5
    assert draft.notional == Decimal("12375")  # 125 * 99


def test_build_order_draft_buy_floors_quantity() -> None:
    inputs = OrderDraftInputs(
        symbol="MSFT",
        side="buy",
        current_price=Decimal("100"),
        atr=Decimal("2"),
        equity=Decimal("1000"),
        risk_fraction=Decimal("0.01"),  # 10 risk budget
        k_entry=Decimal("0"),  # entry = 100
        k_stop=Decimal("2.0"),  # SL = 96 -> risk_per_share = 4
        k_tp=Decimal("3.0"),
    )
    # 10 / 4 = 2.5 -> floor = 2
    draft = build_order_draft(inputs)
    assert draft.quantity == Decimal("2")
    assert draft.risk_amount == Decimal("8")


def test_build_order_draft_buy_zero_quantity_raises_draft_not_viable() -> None:
    inputs = OrderDraftInputs(
        symbol="GOOG",
        side="buy",
        current_price=Decimal("100"),
        atr=Decimal("10"),  # risk_per_share = 20
        equity=Decimal("1000"),
        risk_fraction=Decimal("0.01"),  # risk budget = 10 -> size = floor(10/20) = 0
        k_entry=Decimal("0"),
        k_stop=Decimal("2.0"),
        k_tp=Decimal("3.0"),
    )
    with pytest.raises(DraftNotViable):
        build_order_draft(inputs)


def test_build_order_draft_sell_open_position() -> None:
    inputs = OrderDraftInputs(
        symbol="NVDA",
        side="sell",
        current_price=Decimal("100"),
        atr=Decimal("2"),
        equity=Decimal("50000"),
        risk_fraction=Decimal("0.01"),
        k_entry=Decimal("1.0"),  # mirrored entry = 100 + 1.0*2 = 102
        position_quantity=Decimal("50"),
    )
    draft = build_order_draft(inputs)

    assert draft.symbol == "NVDA"
    assert draft.side == "sell"
    assert draft.entry == Decimal("102")
    assert draft.limit_price == Decimal("102")
    assert draft.quantity == Decimal("50")
    assert draft.notional == Decimal("5100")  # 50 * 102
    assert draft.stop is None
    assert draft.take_profit is None
    assert draft.risk_reward is None
    assert draft.risk_amount is None


def test_build_order_draft_sell_without_position_raises() -> None:
    inputs = OrderDraftInputs(
        symbol="NVDA",
        side="sell",
        current_price=Decimal("100"),
        atr=Decimal("2"),
        equity=Decimal("50000"),
        risk_fraction=Decimal("0.01"),
        position_quantity=None,
    )
    with pytest.raises(ValueError, match="position"):
        build_order_draft(inputs)

    inputs_zero = OrderDraftInputs(
        symbol="NVDA",
        side="sell",
        current_price=Decimal("100"),
        atr=Decimal("2"),
        equity=Decimal("50000"),
        risk_fraction=Decimal("0.01"),
        position_quantity=Decimal("0"),
    )
    with pytest.raises(ValueError, match="position"):
        build_order_draft(inputs_zero)


def test_build_order_draft_draft_hash_deterministic() -> None:
    inputs = OrderDraftInputs(
        symbol="AAPL",
        side="buy",
        current_price=Decimal("100"),
        atr=Decimal("2"),
        equity=Decimal("50000"),
        risk_fraction=Decimal("0.01"),
        k_entry=Decimal("0.5"),
    )
    draft1 = build_order_draft(inputs)
    draft2 = build_order_draft(inputs)

    assert len(draft1.draft_hash) == 64
    assert draft1.draft_hash == draft2.draft_hash

    # Hash changes when price / quantity changes
    inputs_modified = OrderDraftInputs(
        symbol="AAPL",
        side="buy",
        current_price=Decimal("105"),
        atr=Decimal("2"),
        equity=Decimal("50000"),
        risk_fraction=Decimal("0.01"),
        k_entry=Decimal("0.5"),
    )
    draft_modified = build_order_draft(inputs_modified)
    assert draft1.draft_hash != draft_modified.draft_hash


def test_build_order_draft_invalid_inputs() -> None:
    # Invalid side (e.g. short not allowed)
    with pytest.raises(ValueError, match="side"):
        OrderDraftInputs(
            symbol="AAPL",
            side="short",
            current_price=Decimal("100"),
            atr=Decimal("2"),
            equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
        )

    # ATR <= 0
    with pytest.raises(ValueError, match="[Aa][Tt][Rr]"):
        OrderDraftInputs(
            symbol="AAPL",
            side="buy",
            current_price=Decimal("100"),
            atr=Decimal("0"),
            equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
        )

    # Current price <= 0
    with pytest.raises(ValueError, match="current_price"):
        OrderDraftInputs(
            symbol="AAPL",
            side="buy",
            current_price=Decimal("-1"),
            atr=Decimal("2"),
            equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
        )

    # Equity <= 0
    with pytest.raises(ValueError, match="equity"):
        OrderDraftInputs(
            symbol="AAPL",
            side="buy",
            current_price=Decimal("100"),
            atr=Decimal("2"),
            equity=Decimal("0"),
            risk_fraction=Decimal("0.01"),
        )

    # Risk fraction out of bounds
    with pytest.raises(ValueError, match="risk_fraction"):
        OrderDraftInputs(
            symbol="AAPL",
            side="buy",
            current_price=Decimal("100"),
            atr=Decimal("2"),
            equity=Decimal("10000"),
            risk_fraction=Decimal("0"),
        )


def test_build_order_draft_defaults() -> None:
    inputs = OrderDraftInputs(
        symbol="AAPL",
        side="buy",
        current_price=Decimal("100"),
        atr=Decimal("2"),
        equity=Decimal("50000"),
        risk_fraction=Decimal("0.01"),
    )
    assert inputs.k_stop == DEFAULT_K_STOP
    assert inputs.k_tp == DEFAULT_K_TP
