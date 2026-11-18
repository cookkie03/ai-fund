import json
from datetime import UTC, datetime
from urllib.request import Request, urlopen

from interface.dashboard import SQLiteDashboardReadModel
from interface.server import DashboardServer
from storage.sqlite import DecisionRecord, SQLiteDatabase


def test_hourly_calendar_handles_early_close_and_market_timezone():
    from types import SimpleNamespace

    from workflows.market_calendar import alpaca_hourly_timestamps

    class CalendarClient:
        def get_calendar(self, request):
            return [
                SimpleNamespace(
                    open=datetime(2026, 11, 27, 9, 30), close=datetime(2026, 11, 27, 13, 0)
                )
            ]

    timestamps = alpaca_hourly_timestamps(
        CalendarClient(), datetime(2026, 11, 27, tzinfo=UTC), datetime(2026, 11, 28, tzinfo=UTC)
    )
    assert timestamps == tuple(
        datetime(2026, 11, 27, hour, tzinfo=UTC) for hour in (14, 15, 16, 17)
    )


def test_daily_calendar_skips_holidays_and_preserves_session_dates(tmp_path):
    from types import SimpleNamespace

    from workflows.market_calendar import alpaca_daily_timestamps

    class CalendarClient:
        def get_calendar(self, request):
            assert request.start.isoformat() == "2026-11-24"
            return [SimpleNamespace(date=datetime(2026, 11, day).date()) for day in (25, 27, 30)]

    timestamps = alpaca_daily_timestamps(
        CalendarClient(), datetime(2026, 11, 25, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC)
    )
    assert timestamps == tuple(datetime(2026, 11, day, 5, tzinfo=UTC) for day in (25, 27, 30))


def test_http_dashboard_exposes_persisted_decision_queue(tmp_path):
    database = SQLiteDatabase(tmp_path / "server.db")
    database.decisions.save(
        DecisionRecord(
            client_order_id="run-1:AAPL",
            symbol="AAPL",
            status="risk_approved",
            direction="long",
            conviction="buy",
            rationale="trend confirmed",
            observed_at=datetime(2026, 11, 2, 15, tzinfo=UTC),
            payload="run-1",
        )
    )
    database.close()
    server = DashboardServer(SQLiteDashboardReadModel(tmp_path / "server.db"), port=0)
    server.start()

    try:
        with urlopen(Request(server.url("/api/dashboard"), method="GET")) as response:
            payload = json.load(response)
    finally:
        server.close()

    assert payload["decisions"][0]["symbol"] == "AAPL"
    assert payload["modules"]["decisions"] == "available"
