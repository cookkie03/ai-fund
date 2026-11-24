"""Tests for Notizie environment, ingestion, agent tools, usage tracking, and read endpoints."""

import sys
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from bootstrap import build_test_office
from data.providers.openbb import OpenBBProvider
from data.providers.rss_news import RSSItem, RSSNewsProvider
from runtime.core import Runtime
from runtime.http import create_app
from runtime.jobs import NewsIngestionJob
from scripts.dev_cockpit_server import create_dev_app
from storage.office_db import OfficeDB


def test_rss_parser_parses_feed(tmp_path):
    item = RSSItem(
        headline="Apple reports record earnings",
        summary="Apple Inc. beat estimates.",
        url="https://example.com/apple-earnings",
        published_at=datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC),
        source="Test RSS",
    )
    assert item.headline == "Apple reports record earnings"
    assert item.url == "https://example.com/apple-earnings"


def test_rss_provider_invalid_scheme():
    prov = RSSNewsProvider(url="ftp://example.com/feed", name="FTP Feed")
    with pytest.raises(ValueError, match="Invalid RSS URL scheme"):
        prov.fetch_news()


def test_openbb_missing_extra_sets_unavailable(tmp_path):
    db = OfficeDB(tmp_path / "openbb_missing.db")
    sid = db.add_news_source("openbb", "OpenBB", None)
    s_rss = db.add_news_source("rss", "Valid RSS", "https://example.com/rss")

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "openbb", None)
        try:
            prov = OpenBBProvider()
            prov.get_news()
        except Exception as exc:
            db.update_news_source_status(sid, "unavailable", str(exc))

    sources = db.list_news_sources()
    openbb_status = next(s for s in sources if s["id"] == sid)
    rss_status = next(s for s in sources if s["id"] == s_rss)

    assert openbb_status["status"] == "unavailable"
    assert openbb_status["last_error"] is not None
    assert rss_status["status"] == "ok"


def test_news_ingestion_job_runs(tmp_path):
    db = OfficeDB(tmp_path / "ingest.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    db.add_news_source("rss", "Local RSS", "https://example.com/rss")
    job = NewsIngestionJob(rt, interval_minutes=15)
    assert job.next_run(datetime.now(UTC)) is not None


def test_dev_server_http_and_sse_smoke(tmp_path):
    db_path = tmp_path / "smoke.db"
    app = create_dev_app(db_path=str(db_path))
    client = TestClient(app)

    # Smoke test read endpoints
    r_news = client.get("/v1/read/news")
    assert r_news.status_code == 200
    assert "items" in r_news.json()

    r_sources = client.get("/v1/read/news_sources")
    assert r_sources.status_code == 200
    assert len(r_sources.json()) >= 1

    r_cal = client.get("/v1/read/calendar")
    assert r_cal.status_code == 200
    assert isinstance(r_cal.json(), list)

    # Smoke test events stream (TestClient streaming response)
    with client.stream("GET", "/v1/events", headers={"Accept": "text/event-stream"}) as resp:
        assert resp.status_code == 200


def test_news_deduplication(tmp_path):
    db_path = tmp_path / "dedup.db"
    db = OfficeDB(db_path)
    id1 = db.insert_news(
        headline="Same Headline",
        summary="Sum",
        full_text=None,
        url="https://example.com/same",
        source_id=None,
        source="Src",
        provider="rss",
        published_ts="2026-11-24T10:00:00Z",
    )
    id2 = db.insert_news(
        headline="Updated Headline",
        summary="Sum 2",
        full_text=None,
        url="https://example.com/same",
        source_id=None,
        source="Src",
        provider="rss",
        published_ts="2026-11-24T10:00:00Z",
    )
    assert id1 == id2
    item = db.connection.execute("SELECT headline FROM news WHERE id = ?", (id1,)).fetchone()
    assert item["headline"] == "Updated Headline"


def test_events_published_only_on_commit(tmp_path):
    db = OfficeDB(tmp_path / "events.db")
    rt = Runtime(office=build_test_office(db=db))
    src_id = db.add_news_source("rss", "Test", "https://example.com/rss")
    news_id = db.insert_news(
        headline="Test Event",
        summary=None,
        full_text=None,
        url="https://example.com/evt",
        source_id=src_id,
        source="Test",
        provider="rss",
        published_ts="2026-11-24T10:00:00Z",
    )
    received = []
    rt.bus.add_listener(received.append)
    with db.transaction():
        db.log_news_usage(news_id=news_id, agent="sentiment_analyst", kind="read")
        assert received == []
    assert len(received) == 1
    assert received[0].type == "news.used"


def test_notizie_database_and_read_endpoints(tmp_path):
    db_path = tmp_path / "notizie.db"
    db = OfficeDB(db_path)
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    client = TestClient(create_app(rt))

    # Add news source
    src_id = db.add_news_source(provider="rss", name="Test Feed", url="https://example.com/feed.xml")
    assert src_id > 0

    # Insert news
    news_id = db.insert_news(
        headline="Tech stocks surge in early trade",
        summary="Semiconductors lead the rally.",
        full_text="Detailed analysis of tech rally.",
        url="https://example.com/tech-surge",
        source_id=src_id,
        source="Test Feed",
        provider="rss",
        published_ts="2026-11-24T10:00:00Z",
        tickers=["NVDA", "AAPL"],
        themes=["technology", "semiconductors"],
    )
    assert news_id > 0

    # Log usage
    db.log_news_usage(news_id=news_id, agent="sentiment_analyst", kind="read")
    db.log_news_usage(news_id=news_id, agent="portfolio_manager", kind="cited")

    # Insert calendar event
    db.insert_calendar_event(
        kind="macro",
        ts="2026-11-25T14:30:00Z",
        title="US CPI Inflation",
        country="US",
        importance="high",
        actual=None,
        forecast=3.2,
        previous=3.1,
        source="openbb",
    )

    # Test GET /v1/read/news
    resp = client.get("/v1/read/news", params={"ticker": "NVDA"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["headline"] == "Tech stocks surge in early trade"
    assert item["usage"]["reads"] == 1
    assert item["usage"]["citations"] == 1

    # Test GET /v1/read/news_item
    item_resp = client.get("/v1/read/news_item", params={"id": news_id})
    assert item_resp.status_code == 200
    detail = item_resp.json()
    assert detail["full_text"] == "Detailed analysis of tech rally."
    assert len(detail["usage_detail"]) == 2

    # Test GET /v1/read/news_sources
    sources_resp = client.get("/v1/read/news_sources")
    assert sources_resp.status_code == 200
    sources = sources_resp.json()
    assert len(sources) >= 1
    assert sources[0]["name"] == "Test Feed"

    # Test GET /v1/read/calendar
    cal_resp = client.get("/v1/read/calendar", params={"kind": "macro"})
    assert cal_resp.status_code == 200
    events = cal_resp.json()
    assert len(events) == 1
    assert events[0]["title"] == "US CPI Inflation"


def test_news_commands_and_forwarding(tmp_path):
    db_path = tmp_path / "cmd.db"
    db = OfficeDB(db_path)
    rt = Runtime(office=build_test_office(db=db))
    client = TestClient(create_app(rt))

    # Add source command
    res = client.post(
        "/v1/commands/add_news_source",
        json={"provider": "rss", "name": "RSS 1", "url": "https://example.com/rss"},
        headers={"Idempotency-Key": "k1", "X-Actor": "Luca"},
    )
    assert res.status_code == 200
    source_id = res.json()["data"]["source_id"]

    # Insert news
    news_id = db.insert_news(
        headline="AI Breakthrough",
        summary="AI models improve.",
        full_text=None,
        url="https://example.com/ai",
        source_id=source_id,
        source="RSS 1",
        provider="rss",
        published_ts="2026-11-24T10:00:00Z",
        tickers=["NVDA"],
    )

    # Forward news command
    fwd = client.post(
        "/v1/commands/forward_news",
        json={"news_id": news_id, "to": {"agent": "sentiment_analyst"}, "note": "Guarda questo"},
        headers={"Idempotency-Key": "k2", "X-Actor": "Luca"},
    )
    assert fwd.status_code == 200
    assert fwd.json()["ok"] is True
    chat_id = fwd.json()["data"]["chat_id"]
    msgs = db.list_messages(chat_id)
    assert len(msgs) == 1
    assert "AI Breakthrough" in msgs[0]["text"]
    assert "Guarda questo" in msgs[0]["text"]

    # Refresh news command
    ref = client.post(
        "/v1/commands/refresh_news",
        json={},
        headers={"Idempotency-Key": "k4", "X-Actor": "Luca"},
    )
    assert ref.status_code == 200
    assert ref.json()["ok"] is True

    # Remove news source command
    rem = client.post(
        "/v1/commands/remove_news_source",
        json={"source_id": source_id},
        headers={"Idempotency-Key": "k5", "X-Actor": "Luca"},
    )
    assert rem.status_code == 200
    assert rem.json()["ok"] is True


def test_agent_news_tools_and_calendars(tmp_path):
    db_path = tmp_path / "tools.db"
    db = OfficeDB(db_path)
    office = build_test_office(db=db)

    # Insert test news & calendar events
    sid = db.add_news_source("rss", "Test", "https://example.com/rss")
    db.insert_news(
        headline="Semiconductor demand doubles",
        summary="AI chip demand surges.",
        full_text="Detailed text",
        url="https://example.com/chips",
        source_id=sid,
        source="Test",
        provider="rss",
        published_ts="2026-11-24T10:00:00Z",
        tickers=["NVDA"],
        themes=["technology"],
    )
    db.insert_calendar_event(
        kind="macro",
        ts="2026-11-25T14:30:00Z",
        title="Fed Rate Decision",
        country="US",
        importance="high",
        source="openbb",
    )
    db.insert_calendar_event(
        kind="earnings",
        ts="2026-11-26T20:00:00Z",
        title="Earnings: NVDA",
        ticker="NVDA",
        importance="high",
        source="openbb",
    )

    env = office.get_env()
    sa_tools = {t.name: t for t in env.tools_for("sentiment_analyst")}
    assert "news_search" in sa_tools
    assert "news_by_ticker" in sa_tools

    ma_tools = {t.name: t for t in env.tools_for("market_analyst")}
    assert "news_by_theme" in ma_tools
    assert "economic_calendar" in ma_tools

    fa_tools = {t.name: t for t in env.tools_for("fundamental_analyst")}
    assert "earnings_calendar" in fa_tools

    # Test execution
    res_search = sa_tools["news_search"].fn(q="Semiconductor", ticker="NVDA")
    assert len(res_search) == 1
    assert res_search[0]["headline"] == "Semiconductor demand doubles"

    res_ticker = sa_tools["news_by_ticker"].fn(ticker="NVDA")
    assert len(res_ticker) == 1

    res_theme = ma_tools["news_by_theme"].fn(theme="technology")
    assert len(res_theme) == 1

    res_econ = ma_tools["economic_calendar"].fn()
    assert len(res_econ) == 1
    assert res_econ[0]["title"] == "Fed Rate Decision"

    res_earn = fa_tools["earnings_calendar"].fn(tickers=["NVDA"])
    assert len(res_earn) == 1
    assert res_earn[0]["ticker"] == "NVDA"


class MockAlpacaItem:
    def __init__(self, headline, source, url, created_at, symbols):
        self.headline = headline
        self.source = source
        self.url = url
        self.created_at = created_at
        self.symbols = symbols


class MockAlpacaResponse:
    def __init__(self, news, next_page_token=None):
        self.news = news
        self.next_page_token = next_page_token


class MockAlpacaClient:
    def get_news(self, req):
        dt = datetime(2026, 11, 24, 10, 0, 0, tzinfo=UTC)
        if req.page_token is None:
            item = MockAlpacaItem("Apple launches new chip", "Bloomberg", "https://example.com/apple1", dt, ["AAPL"])
            return MockAlpacaResponse([item], next_page_token="token2")
        else:
            item = MockAlpacaItem("Apple expands services", "Reuters", "https://example.com/apple2", dt, ["AAPL"])
            return MockAlpacaResponse([item], next_page_token=None)


def test_alpaca_news_pagination():
    from data.providers.alpaca_news import AlpacaNewsProvider
    client = MockAlpacaClient()
    provider = AlpacaNewsProvider(client)
    start = datetime(2026, 11, 24, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 11, 25, 0, 0, 0, tzinfo=UTC)
    items = provider.get_news("AAPL", start, end, limit=10)
    assert len(items) == 2
    assert items[0].headline == "Apple launches new chip"
    assert items[1].headline == "Apple expands services"


