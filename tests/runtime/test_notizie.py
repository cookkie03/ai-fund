"""Tests for Notizie environment, ingestion, agent tools, usage tracking, and read endpoints."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from bootstrap import build_test_office
from data.providers.rss_news import RSSItem, RSSNewsProvider
from runtime.core import Runtime
from runtime.http import create_app
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

    # Disable source
    dis = client.post(
        "/v1/commands/set_news_source_enabled",
        json={"source_id": source_id, "enabled": 0},
        headers={"Idempotency-Key": "k3", "X-Actor": "Luca"},
    )
    assert dis.status_code == 200
    assert dis.json()["ok"] is True
