"""Fake broker stream for testing trade updates and reconnect reconciliation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FakeBrokerStream:
    """In-memory fake stream implementing broker stream lifecycle."""

    def __init__(
        self,
        on_trade_update: Callable[[Any], None] | None = None,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        self.on_trade_update = on_trade_update
        self.on_reconnect = on_reconnect
        self.running = False

    @property
    def connected(self) -> bool:
        return self.running

    def start(self) -> None:
        self.running = True
        if self.on_reconnect is not None:
            self.on_reconnect()

    def stop(self) -> None:
        self.running = False

    def simulate_trade_update(self, update: Any) -> None:
        if self.on_trade_update is not None:
            self.on_trade_update(update)

    def simulate_reconnect(self) -> None:
        if self.on_reconnect is not None:
            self.on_reconnect()
