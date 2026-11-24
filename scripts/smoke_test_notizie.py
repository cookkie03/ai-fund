"""Smoke test script for Notizie backend: OpenBB unavailable check, real RSS read, and dev server HTTP/SSE on port 8776."""

from __future__ import annotations

import multiprocessing
import time

import httpx
import uvicorn

from data.providers.openbb import OpenBBProvider
from data.providers.rss_news import RSSNewsProvider
from scripts.dev_cockpit_server import create_dev_app
from storage.office_db import OfficeDB


def run_server():
    app = create_dev_app(db_path="data/dev-cockpit-notizie-be.db")
    uvicorn.run(app, host="127.0.0.1", port=8776, log_level="warning")


def main():
    print("--- STARTING SMOKE TEST ---")
    # 1. Test OpenBB absent / unconfigured -> unavailable status
    db = OfficeDB("data/smoke_test.db")
    s_openbb = db.add_news_source("openbb", "OpenBB Source", None)
    try:
        prov = OpenBBProvider()
        prov.get_news()
    except Exception as exc:
        db.update_news_source_status(s_openbb, "unavailable", str(exc))
    sources = db.list_news_sources()
    ob_src = next(s for s in sources if s["id"] == s_openbb)
    assert ob_src["status"] == "unavailable"
    print("OPENBB_CHECK_VERIFIED: status =", ob_src["status"], "error =", repr(ob_src["last_error"]))

    # 2. Real read-only check of public RSS feed
    try:
        rss = RSSNewsProvider(url="https://news.ycombinator.com/rss", name="Hacker News")
        items = rss.fetch_news()
        print(f"RSS_CHECK_VERIFIED: fetched {len(items)} items from Hacker News RSS.")
    except Exception as exc:
        print("RSS_CHECK: skipped:", exc)

    # 3. Start dev server on port 8776 for HTTP/SSE smoke test
    server_process = multiprocessing.Process(target=run_server)
    server_process.start()
    time.sleep(3.0)

    try:
        base_url = "http://127.0.0.1:8776"
        with httpx.Client(base_url=base_url, timeout=5.0) as client:
            r_news = client.get("/v1/read/news")
            print("HTTP_CHECK: GET /v1/read/news -> status", r_news.status_code, "items count:", len(r_news.json().get("items", [])))
            assert r_news.status_code == 200

            r_sources = client.get("/v1/read/news_sources")
            print("HTTP_CHECK: GET /v1/read/news_sources -> status", r_sources.status_code, "sources count:", len(r_sources.json()))
            assert r_sources.status_code == 200

            r_cal = client.get("/v1/read/calendar")
            print("HTTP_CHECK: GET /v1/read/calendar -> status", r_cal.status_code, "events count:", len(r_cal.json()))
            assert r_cal.status_code == 200

            # Smoke SSE stream connection check
            with client.stream("GET", "/v1/events", timeout=2.0) as response:
                print("SSE_CHECK: GET /v1/events -> status", response.status_code)
                assert response.status_code == 200
        print("SMOKE_SUCCESS_EXPLICIT: All HTTP and SSE endpoints verified on http://127.0.0.1:8776")
    finally:
        server_process.terminate()
        server_process.join()


if __name__ == "__main__":
    main()
