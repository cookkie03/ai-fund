"""AlpacaBracketAdapter modifica le gambe stop/take-profit, mai il limite d'ingresso."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from bootstrap import AlpacaBracketAdapter


class _Client:
    def __init__(self):
        self.replaced: list[tuple[str, object]] = []
        self.parent = SimpleNamespace(
            id="parent",
            legs=[
                SimpleNamespace(id="tp-leg", order_type="limit"),
                SimpleNamespace(id="sl-leg", order_type="stop"),
            ],
        )

    def get_order_by_id(self, order_id):
        return self.parent

    def replace_order_by_id(self, order_id, request):
        self.replaced.append((order_id, request))


def test_modify_stop_targets_stop_leg():
    client = _Client()
    AlpacaBracketAdapter(client).modify_stop("parent", Decimal("320.42"))
    assert client.replaced[0][0] == "sl-leg"
    assert client.replaced[0][1].stop_price == 320.42


def test_modify_take_profit_targets_limit_leg():
    client = _Client()
    AlpacaBracketAdapter(client).modify_take_profit("parent", Decimal("394.36"))
    assert client.replaced[0][0] == "tp-leg"
    assert client.replaced[0][1].limit_price == 394.36


def test_missing_leg_raises():
    client = _Client()
    client.parent.legs = []
    with pytest.raises(RuntimeError):
        AlpacaBracketAdapter(client).modify_stop("parent", Decimal("1"))
