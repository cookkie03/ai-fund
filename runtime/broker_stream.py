"""Broker trade update streaming interface and Alpaca implementation."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class BrokerUpdateStream(Protocol):
    """Protocol for streaming broker updates and handling reconnection."""

    @property
    def connected(self) -> bool:
        """Return True if stream is currently connected and active."""
        ...

    def start(self) -> None:
        """Start the background stream."""
        ...

    def stop(self) -> None:
        """Stop the background stream."""
        ...


class AlpacaTradeUpdateStream:
    """Manages the background Alpaca websocket stream for trade updates."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
        on_trade_update: Callable[[Any], None] | None = None,
        on_reconnect: Callable[[], None] | None = None,
        trading_url: str | None = None,
        backoff_initial: float = 1.0,
        backoff_max: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.trading_url = trading_url
        self.on_trade_update = on_trade_update
        self.on_reconnect = on_reconnect
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max

        self._thread: threading.Thread | None = None
        self._running = False
        self._connected = False
        self._stream: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def connected(self) -> bool:
        return self._connected and self._running

    def start(self) -> None:
        """Start the background streaming thread and trigger initial reconciliation."""
        if self._running:
            return
        self._running = True

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="alpaca-stream")
        self._thread.start()

    def _run_loop(self) -> None:
        backoff = self.backoff_initial
        while self._running:
            try:
                from alpaca.trading.stream import TradingStream

                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)

                url_override = None
                if self.trading_url and not self.paper:
                    # live url override if needed
                    url_override = self.trading_url

                self._stream = TradingStream(
                    api_key=self.api_key,
                    secret_key=self.secret_key,
                    paper=self.paper,
                    url_override=url_override,
                )

                async def _handler(data: Any) -> None:
                    if self.on_trade_update is not None:
                        try:
                            self.on_trade_update(data)
                        except Exception:
                            logger.exception("Error handling trade update: %s", data)

                self._stream.subscribe_trade_updates(_handler)
                self._connected = True
                backoff = self.backoff_initial

                if self.on_reconnect is not None:
                    try:
                        self.on_reconnect()
                    except Exception:
                        logger.exception("Broker reconciliation failed on (re)connect")

                self._stream.run()
            except Exception as exc:
                self._connected = False
                if self._running:
                    logger.error("Alpaca stream disconnected: %s. Retrying in %.1fs", exc, backoff)
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, self.backoff_max)
            finally:
                self._connected = False
                if self._loop is not None and not self._loop.is_closed():
                    try:
                        self._loop.close()
                    except Exception:
                        pass

    def stop(self) -> None:
        """Stop the stream and wait for background thread to exit."""
        self._running = False
        self._connected = False
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
