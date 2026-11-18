"""CacheMarketDataAdapter: ultime barre in ordine cronologico, nessun prezzo inventato."""

import pytest

from bootstrap import CacheMarketDataAdapter


class _Bars(list):
    pass


class _Cache:
    def __init__(self, rows):
        self.rows = rows

    def get(self, kind, key=None, **kwargs):
        return _Bars(self.rows)


def _bar(i):
    return {"ts": f"2026-01-{i:02d}T00:00:00Z", "o": i, "h": i + 1, "l": i - 1, "c": i, "v": 10}


def test_ohlcv_returns_latest_bars_in_ascending_order():
    adapter = CacheMarketDataAdapter(_Cache([_bar(i) for i in range(1, 11)]))
    bars = adapter.ohlcv("AAPL", "1d", 3)
    assert [b["c"] for b in bars] == [8, 9, 10]


def test_quote_uses_latest_bar():
    adapter = CacheMarketDataAdapter(_Cache([_bar(i) for i in range(1, 6)]))
    assert adapter.quote("aapl")["price"] == 5.0


def test_quote_without_data_raises_instead_of_inventing_a_price():
    adapter = CacheMarketDataAdapter(_Cache([]))
    with pytest.raises(RuntimeError):
        adapter.quote("AAPL")
