"""Adapter OpenBB verso il contratto interno di dati di mercato."""

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from ..models import PriceBar


class OpenBBProvider:
    """Normalizza lo storico OpenBB nel contratto interno.

    OpenBB è un adapter sostituibile, non il contratto del core: nessun tipo
    o namespace OpenBB deve attraversare questo modulo.
    """

    def __init__(
        self,
        client: Any | None = None,
        provider: str = "yfinance",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client if client is not None else _load_openbb_client()
        self._provider = provider
        self._clock = clock

    def get_ohlcv_history(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> tuple[PriceBar, ...]:
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol must not be blank")
        _require_aware_utc(start, "start")
        _require_aware_utc(end, "end")
        if start >= end:
            raise ValueError("start must be earlier than end")

        response = self._client.equity.price.historical(
            symbol=symbol,
            start_date=start.date().isoformat(),
            end_date=end.date().isoformat(),
            provider=self._provider,
            interval=interval,
        )
        rows = _rows(response)
        collected_at = self._clock()
        _require_aware_utc(collected_at, "clock result")
        return tuple(
            PriceBar(
                symbol=symbol,
                interval=interval,
                timestamp=_as_utc(row["date"]),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
                source=f"openbb:{self._provider}",
                collected_at=collected_at,
                reference_date=_as_utc(row["date"]),
            )
            for row in rows
        )

    def get_news(self, symbol: str | None = None, start: datetime | None = None, end: datetime | None = None) -> tuple[Any, ...]:
        try:
            if symbol:
                res = self._client.news.company(symbol=symbol.upper().strip(), provider=self._provider)
            else:
                res = self._client.news.world(provider=self._provider)
            rows = _rows(res)
            items = []
            for r in rows:
                title = r.get("title") or r.get("headline")
                url = r.get("url") or r.get("link")
                pub = r.get("date") or r.get("published_at") or r.get("created_at")
                if title and url:
                    items.append({
                        "headline": title.strip(),
                        "summary": r.get("text") or r.get("summary"),
                        "url": url.strip(),
                        "published_at": _as_utc(pub) if pub else datetime.now(UTC),
                        "source": r.get("source", "openbb"),
                    })
            return tuple(items)
        except Exception as exc:
            raise RuntimeError(f"OpenBB news unavailable: {exc}") from exc

    def get_econ_calendar(self, start: datetime | None = None, end: datetime | None = None) -> tuple[Any, ...]:
        try:
            res = self._client.economy.calendar(provider=self._provider)
            rows = _rows(res)
            items = []
            for r in rows:
                title = r.get("event") or r.get("title") or r.get("name")
                dt = r.get("date") or r.get("time") or r.get("timestamp")
                if title and dt:
                    items.append({
                        "kind": "macro",
                        "ts": _as_utc(dt).isoformat(),
                        "title": str(title).strip(),
                        "country": r.get("country"),
                        "importance": r.get("importance"),
                        "actual": float(r["actual"]) if r.get("actual") is not None and str(r["actual"]) != "" else None,
                        "forecast": float(r["forecast"]) if r.get("forecast") is not None and str(r["forecast"]) != "" else None,
                        "previous": float(r["previous"]) if r.get("previous") is not None and str(r["previous"]) != "" else None,
                        "source": f"openbb:{self._provider}",
                    })
            return tuple(items)
        except Exception as exc:
            raise RuntimeError(f"OpenBB econ calendar unavailable: {exc}") from exc

    def get_earnings_calendar(self, start: datetime | None = None, end: datetime | None = None, tickers: list[str] | None = None) -> tuple[Any, ...]:
        try:
            kwargs = {"provider": self._provider}
            if tickers:
                kwargs["symbol"] = ",".join(tickers)
            res = self._client.equity.calendar.earnings(**kwargs)
            rows = _rows(res)
            items = []
            for r in rows:
                symbol = r.get("symbol") or r.get("ticker")
                dt = r.get("date") or r.get("report_date") or r.get("time")
                if symbol and dt:
                    items.append({
                        "kind": "earnings",
                        "ts": _as_utc(dt).isoformat(),
                        "title": f"Earnings: {symbol.upper()}",
                        "ticker": symbol.upper(),
                        "importance": "high",
                        "actual": float(r["eps_actual"]) if r.get("eps_actual") is not None and str(r["eps_actual"]) != "" else None,
                        "forecast": float(r["eps_estimated"]) if r.get("eps_estimated") is not None and str(r["eps_estimated"]) != "" else None,
                        "source": f"openbb:{self._provider}",
                    })
            return tuple(items)
        except Exception as exc:
            raise RuntimeError(f"OpenBB earnings calendar unavailable: {exc}") from exc


def _load_openbb_client() -> Any:
    try:
        from openbb import obb
    except ImportError as error:
        raise RuntimeError(
            "OpenBB is not installed; install the project's OpenBB extra to use OpenBBProvider"
        ) from error
    return obb


def _rows(response: Any) -> Iterable[Mapping[str, Any]]:
    dataframe = response.to_df()
    if hasattr(dataframe, "to_dict"):
        if hasattr(dataframe, "reset_index"):
            dataframe = dataframe.reset_index()
        records = dataframe.to_dict("records")
        for record in records:
            if "Date" in record and "date" not in record:
                record["date"] = record.pop("Date")
        return records
    return dataframe


def _as_utc(value: Any) -> datetime:
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time.min)
    elif hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        raise TypeError("OpenBB response dates must be date or datetime values")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_aware_utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
