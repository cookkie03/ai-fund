"""FakeBracketBroker: in-memory bracket broker fake for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class FakeBrokerOrder:
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: Decimal
    limit_price: Decimal
    take_profit: Decimal | None
    stop_loss: Decimal | None
    status: str = "open"  # "open", "submitted", "filled", "cancelled", "rejected"
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None


@dataclass
class FakeBracketBroker:
    """In-memory fake implementing BracketBroker Protocol."""

    market_open: bool = True
    orders: dict[str, FakeBrokerOrder] = field(default_factory=dict)
    client_map: dict[str, str] = field(default_factory=dict)  # client_order_id -> broker_order_id
    cancelled_orders: list[str] = field(default_factory=list)
    modified_stops: list[tuple[str, Decimal]] = field(default_factory=list)
    modified_take_profits: list[tuple[str, Decimal]] = field(default_factory=list)
    market_prices: dict[str, Decimal] = field(default_factory=dict)
    closed_positions: list[dict] = field(default_factory=list)
    _order_counter: int = 0

    def is_market_open(self) -> bool:
        return self.market_open

    def submit_bracket(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        limit_price: Decimal,
        take_profit: Decimal,
        stop_loss: Decimal,
    ) -> str:
        if client_order_id in self.client_map:
            return self.client_map[client_order_id]

        self._order_counter += 1
        broker_order_id = f"b_ord_{self._order_counter:04d}"
        order = FakeBrokerOrder(
            broker_order_id=broker_order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            quantity=Decimal(str(qty)),
            limit_price=Decimal(str(limit_price)),
            take_profit=Decimal(str(take_profit)) if take_profit is not None else None,
            stop_loss=Decimal(str(stop_loss)) if stop_loss is not None else None,
            status="submitted",
        )
        self.orders[broker_order_id] = order
        self.client_map[client_order_id] = broker_order_id
        return broker_order_id

    def modify_stop(self, broker_order_id: str, stop: Decimal) -> None:
        if broker_order_id not in self.orders:
            raise KeyError(f"Broker order {broker_order_id} not found")
        self.orders[broker_order_id].stop_loss = Decimal(str(stop))
        self.modified_stops.append((broker_order_id, Decimal(str(stop))))

    def modify_take_profit(self, broker_order_id: str, take_profit: Decimal) -> None:
        if broker_order_id not in self.orders:
            raise KeyError(f"Broker order {broker_order_id} not found")
        self.orders[broker_order_id].take_profit = Decimal(str(take_profit))
        self.modified_take_profits.append((broker_order_id, Decimal(str(take_profit))))

    def cancel(self, broker_order_id: str) -> None:
        if broker_order_id not in self.orders:
            raise KeyError(f"Broker order {broker_order_id} not found")
        self.orders[broker_order_id].status = "cancelled"
        self.cancelled_orders.append(broker_order_id)

    def close_position(
        self,
        *,
        client_order_id: str,
        symbol: str,
        qty: Decimal,
        order_type: str,
        limit_price: Decimal | None,
        bracket_order_id: str | None,
        residual_qty: Decimal,
        residual_stop: Decimal | None,
        residual_target: Decimal | None,
    ):
        """Vendita immediata al prezzo di mercato configurato; il bracket diventa residuo."""
        from execution.position_exits import CloseResult

        price = Decimal(str(limit_price)) if order_type == "limit" and limit_price is not None \
            else self.market_prices.get(symbol)
        if price is None:
            raise RuntimeError(f"Nessun prezzo di mercato per {symbol}")
        if bracket_order_id and bracket_order_id in self.orders:
            self.orders[bracket_order_id].status = "cancelled"
            self.cancelled_orders.append(bracket_order_id)
        self._order_counter += 1
        sell_id = f"b_ord_{self._order_counter:04d}"
        self.orders[sell_id] = FakeBrokerOrder(
            broker_order_id=sell_id, client_order_id=client_order_id, symbol=symbol, side="sell",
            quantity=Decimal(str(qty)), limit_price=price, take_profit=None, stop_loss=None,
            status="filled", filled_quantity=Decimal(str(qty)), average_fill_price=price,
        )
        self.client_map[client_order_id] = sell_id
        residual_id = None
        if residual_qty > 0:
            self._order_counter += 1
            residual_id = f"b_ord_{self._order_counter:04d}"
            self.orders[residual_id] = FakeBrokerOrder(
                broker_order_id=residual_id, client_order_id=f"{client_order_id}-res",
                symbol=symbol, side="buy", quantity=Decimal(str(residual_qty)),
                limit_price=price, take_profit=residual_target, stop_loss=residual_stop,
                status="filled", filled_quantity=Decimal(str(residual_qty)),
                average_fill_price=price,
            )
        self.closed_positions.append({"symbol": symbol, "qty": Decimal(str(qty)), "price": price})
        return CloseResult(broker_order_id=sell_id, status="filled", fill_price=price,
                           filled_qty=Decimal(str(qty)), residual_order_id=residual_id)

    def find_by_client_id(self, client_order_id: str) -> FakeBrokerOrder | None:
        b_id = self.client_map.get(client_order_id)
        if b_id is None:
            return None
        return self.orders.get(b_id)

    def get_order(self, broker_order_id: str) -> FakeBrokerOrder | None:
        return self.orders.get(broker_order_id)

    def get_open_orders(self, symbol: str | None = None) -> list[FakeBrokerOrder]:
        return [
            o
            for o in self.orders.values()
            if o.status in ("open", "submitted") and (symbol is None or o.symbol == symbol)
        ]

    # --- Test helper methods ---

    def fill_order(
        self,
        broker_order_id: str,
        fill_price: Decimal | float | None = None,
        fill_qty: Decimal | float | None = None,
    ) -> FakeBrokerOrder:
        order = self.orders[broker_order_id]
        order.status = "filled"
        order.filled_quantity = (
            Decimal(str(fill_qty)) if fill_qty is not None else order.quantity
        )
        order.average_fill_price = (
            Decimal(str(fill_price)) if fill_price is not None else order.limit_price
        )
        return order
