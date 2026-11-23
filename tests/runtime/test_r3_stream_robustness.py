"""Test R3: Broker stream reconnect loop with backoff and reconciliation, real connected state, paper derivation."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from bootstrap import build_test_office
from runtime.broker_stream import AlpacaTradeUpdateStream, BrokerUpdateStream
from runtime.core import Runtime
from storage.office_db import OfficeDB


def test_r3_stream_implements_protocol():
    """AlpacaTradeUpdateStream must implement BrokerUpdateStream protocol."""
    stream = AlpacaTradeUpdateStream(
        api_key="key",
        secret_key="secret",
        paper=True,
    )
    assert isinstance(stream, BrokerUpdateStream)
    assert hasattr(stream, "connected")
    assert stream.connected is False


def test_r3_reconnection_loop_calls_reconcile_on_each_connect():
    """Stream reconnects after error and triggers reconciliation callback each time."""
    reconcile_calls = []

    def _on_reconnect():
        reconcile_calls.append(time.monotonic())

    stream = AlpacaTradeUpdateStream(
        api_key="key",
        secret_key="secret",
        paper=True,
        on_reconnect=_on_reconnect,
        backoff_initial=0.01,
        backoff_max=0.05,
    )

    run_attempts = 0

    class MockTradingStream:
        def __init__(self, *args, **kwargs):
            pass

        def subscribe_trade_updates(self, handler):
            pass

        def run(self):
            nonlocal run_attempts
            run_attempts += 1
            if run_attempts == 1:
                raise ConnectionError("Temporary websocket disconnect")
            elif run_attempts == 2:
                # Keep running briefly then stop
                time.sleep(0.05)
                return

        def stop(self):
            pass

    with patch("alpaca.trading.stream.TradingStream", MockTradingStream):
        stream.start()
        time.sleep(0.12)
        stream.stop()

    assert run_attempts >= 2
    assert len(reconcile_calls) >= 2


def test_r3_health_reports_real_connection_state_changes(tmp_path):
    """Health reports connected=True only when stream is truly active, and False when stopped."""
    db = OfficeDB(tmp_path / "test.db")
    office = build_test_office(db=db)

    fake_stream = MagicMock()
    fake_stream.connected = False

    rt = Runtime(office=office, broker_stream=fake_stream)
    rt.start()
    try:
        assert rt.read.health().broker_stream_connected is False

        # Now simulate connection established
        fake_stream.connected = True
        assert rt.read.health().broker_stream_connected is True

        # Now simulate disconnect
        fake_stream.connected = False
        assert rt.read.health().broker_stream_connected is False
    finally:
        rt.stop()
