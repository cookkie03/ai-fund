"""Alpaca TradeUpdate WebSocket Stream."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class AlpacaTradeUpdateStream:
    """Manages the background Alpaca websocket stream for trade updates."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        on_trade_update: Callable[[Any], None] | None = None,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.on_trade_update = on_trade_update
        self.on_reconnect = on_reconnect
        self._thread: threading.Thread | None = None
        self._running = False
        self._stream: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        """Start the background streaming thread and trigger initial reconciliation."""
        if self._running:
            return
        self._running = True

        if self.on_reconnect is not None:
            try:
                self.on_reconnect()
            except Exception:
                logger.exception("Initial broker reconciliation failed")

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="alpaca-stream")
        self._thread.start()

    def _run_loop(self) -> None:
        try:
            from alpaca.trading.stream import TradingStream

            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            self._stream = TradingStream(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )

            async def _handler(data: Any) -> None:
                if self.on_trade_update is not None:
                    try:
                        self.on_trade_update(data)
                    except Exception:
                        logger.exception("Error handling trade update: %s", data)

            self._stream.subscribe_trade_updates(_handler)
            self._stream.run()
        except Exception as exc:
            if self._running:
                logger.error("Alpaca stream disconnected: %s", exc)
                # Attempt reconnect hook if configured
                if self.on_reconnect is not None:
                    try:
                        self.on_reconnect()
                    except Exception:
                        logger.exception("Reconnect broker reconciliation failed")

    def stop(self) -> None:
        """Stop the stream and wait for background thread to exit."""
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
