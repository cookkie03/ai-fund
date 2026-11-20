"""Backward compatibility redirect for AlpacaTradeUpdateStream."""

from runtime.broker_stream import AlpacaTradeUpdateStream, BrokerUpdateStream

__all__ = ["AlpacaTradeUpdateStream", "BrokerUpdateStream"]
