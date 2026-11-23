"""Test R1: Broker stream configuration, startup reconciliation without stream, and health reporting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from bootstrap import build_test_office
from runtime.core import Runtime
from storage.office_db import OfficeDB


def test_r1_from_settings_reads_alpaca_api_key_and_secret(tmp_path):
    """Runtime.from_settings must read ALPACA_API_KEY and ALPACA_SECRET_KEY, not APCA_*."""
    env = {
        "ALPACA_API_KEY": "test_alpaca_key",
        "ALPACA_SECRET_KEY": "test_alpaca_secret",
        "ALPACA_TRADING_URL": "https://paper-api.alpaca.markets/v2",
        "TRADING_AGENT_DB": str(tmp_path / "test.db"),
    }
    with patch("runtime.broker_stream.AlpacaTradeUpdateStream") as mock_stream_cls:
        mock_instance = MagicMock()
        mock_stream_cls.return_value = mock_instance
        rt = Runtime.from_settings(env=env)
        assert rt.broker_stream is not None
        mock_stream_cls.assert_called_once()
        call_kwargs = mock_stream_cls.call_args[1]
        assert call_kwargs.get("api_key") == "test_alpaca_key"
        assert call_kwargs.get("secret_key") == "test_alpaca_secret"
        assert call_kwargs.get("paper") is True


def test_r1_startup_reconciles_even_without_stream(tmp_path):
    """Runtime.start() must run broker reconciliation even when broker_stream is None."""
    db = OfficeDB(tmp_path / "test.db")
    office = build_test_office(db=db)
    office.order_flow.sync_broker_orders = MagicMock()
    office.refresh_data = MagicMock()

    rt = Runtime(office=office, broker_stream=None)
    rt.start()
    try:
        office.order_flow.sync_broker_orders.assert_called_once()
        office.refresh_data.assert_called_with(force=False, kinds=["portfolio"])
    finally:
        rt.stop()


def test_r1_health_reports_broker_state_when_stream_fails(tmp_path):
    """If broker credentials exist but stream fails to connect, health() must report it."""
    db = OfficeDB(tmp_path / "test.db")
    office = build_test_office(db=db)
    failing_stream = MagicMock()
    failing_stream.start.side_effect = RuntimeError("Connection refused")
    failing_stream.connected = False

    rt = Runtime(office=office, broker_stream=failing_stream)
    rt.broker_configured = True
    rt.start()
    try:
        health = rt.read.health()
        assert health.broker_stream_connected is False
        assert getattr(health, "broker_configured", False) is True
    finally:
        rt.stop()
