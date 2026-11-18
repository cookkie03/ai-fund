"""Tests for market data provider selection and fallback in DataCache."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from bootstrap import _lazy_init_data_cache
from data.cache import DataCache
from storage.office_db import OfficeDB


class FakeYahooFinanceProvider:
    """Trivial fake for YahooFinanceProvider without network dependencies."""

    def get_ohlcv_history(
        self,
        symbol: str,
        start: Any = None,
        end: Any = None,
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        return [{"provider": "yahoo", "symbol": symbol}]


class FakeOpenBBProvider:
    """Trivial fake for OpenBBProvider without network dependencies."""

    def get_ohlcv_history(
        self,
        symbol: str,
        start: Any = None,
        end: Any = None,
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        return [{"provider": "openbb", "symbol": symbol}]


class FailingOpenBBProvider:
    """Fake OpenBBProvider whose constructor raises an error."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("OpenBB SDK not installed or failed to initialize")


def _get_underlying_provider(cache: DataCache, kind: str = "prices_ohlcv") -> Any:
    """Extract the underlying provider instance from an adapted DataCache fetcher."""
    fetcher = cache.providers.get(kind)
    if fetcher is None:
        return None
    closure = fetcher.__closure__
    if not closure:
        return None
    mapping: Mapping[str, Any] = {
        name: cell.cell_contents
        for name, cell in zip(fetcher.__code__.co_freevars, closure, strict=False)
    }
    return mapping.get("provider")


def test_default_env_selects_yahoo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "data.providers.yahoo_finance.YahooFinanceProvider", FakeYahooFinanceProvider
    )
    db = OfficeDB(tmp_path / "x.db")
    try:
        cache = _lazy_init_data_cache(db, {})
        assert "prices_ohlcv" in cache.providers
        provider_instance = _get_underlying_provider(cache)
        assert isinstance(provider_instance, FakeYahooFinanceProvider)
        assert cache.providers["prices_ohlcv"]("AAPL") == [{"provider": "yahoo", "symbol": "AAPL"}]
    finally:
        db.close()


def test_openbb_env_selects_openbb(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("data.providers.openbb.OpenBBProvider", FakeOpenBBProvider)
    monkeypatch.setattr(
        "data.providers.yahoo_finance.YahooFinanceProvider", FakeYahooFinanceProvider
    )
    db = OfficeDB(tmp_path / "x.db")
    try:
        cache = _lazy_init_data_cache(db, {"DATA_PRICES_PROVIDER": "openbb"})
        assert "prices_ohlcv" in cache.providers
        provider_instance = _get_underlying_provider(cache)
        assert isinstance(provider_instance, FakeOpenBBProvider)
        assert cache.providers["prices_ohlcv"]("AAPL") == [{"provider": "openbb", "symbol": "AAPL"}]
    finally:
        db.close()


def test_openbb_fallback_to_yahoo_on_init_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("data.providers.openbb.OpenBBProvider", FailingOpenBBProvider)
    monkeypatch.setattr(
        "data.providers.yahoo_finance.YahooFinanceProvider", FakeYahooFinanceProvider
    )
    db = OfficeDB(tmp_path / "x.db")
    try:
        cache = _lazy_init_data_cache(db, {"DATA_PRICES_PROVIDER": "openbb"})
        assert "prices_ohlcv" in cache.providers
        provider_instance = _get_underlying_provider(cache)
        assert isinstance(provider_instance, FakeYahooFinanceProvider)
        assert cache.providers["prices_ohlcv"]("AAPL") == [{"provider": "yahoo", "symbol": "AAPL"}]
    finally:
        db.close()
