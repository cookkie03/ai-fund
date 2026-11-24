"""Periodic and scheduled jobs for the event-driven runtime scheduler."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.core import Runtime

logger = logging.getLogger(__name__)


def _get_last_run(runtime: Runtime, job_name: str) -> datetime | None:
    try:
        row = runtime.office.db.connection.execute(
            """
            SELECT payload, ts FROM events
            WHERE type = 'job.ran' AND subject = ?
            ORDER BY id DESC LIMIT 1
            """,
            (f"job:{job_name}",),
        ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload"]) if row["payload"] else {}
        ts_str = payload.get("ts") or row["ts"]
        ts_str = str(ts_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except Exception:
        logger.exception("Error reading last run for %s", job_name)
        return None


def _record_job_run(runtime: Runtime, job_name: str, now: datetime) -> None:
    try:
        now_dt = now if now.tzinfo else now.replace(tzinfo=UTC)
        with runtime.office.db.transaction():
            runtime.event_log.append(
                type="job.ran",
                subject=f"job:{job_name}",
                payload={"job": job_name, "ts": now_dt.isoformat()},
                actor="scheduler",
            )
    except Exception:
        logger.exception("Failed to record job.ran event for %s", job_name)


class Job(ABC):
    """Abstract base class for scheduled recurring jobs."""

    name: str

    @abstractmethod
    def next_run(self, now: datetime) -> datetime | None:
        """Return the next datetime when this job should run, or None if not scheduled."""
        ...

    @abstractmethod
    def run(self, now: datetime) -> None:
        """Execute the job."""
        ...


class DataRefreshJob(Job):
    """Hourly market and portfolio data pre-fetch."""

    name = "data_refresh"

    def __init__(self, runtime: Runtime, interval_hours: float = 1.0) -> None:
        self.runtime = runtime
        self.interval = timedelta(hours=interval_hours)

    def next_run(self, now: datetime) -> datetime | None:
        now_dt = now if now.tzinfo else now.replace(tzinfo=UTC)
        last = _get_last_run(self.runtime, self.name)
        if last is None:
            return now_dt
        target = last + self.interval
        return target if target > now_dt else now_dt

    def run(self, now: datetime) -> None:
        _record_job_run(self.runtime, self.name, now)
        try:
            self.runtime.office.refresh_data(force=False)
        except Exception:
            logger.exception("Error executing DataRefreshJob")

class NewsIngestionJob(Job):
    name = "news_ingestion"

    def __init__(self, runtime: Runtime, interval_minutes: float = 15.0) -> None:
        self.runtime = runtime
        self.interval = timedelta(minutes=interval_minutes)

    def next_run(self, now: datetime) -> datetime | None:
        now_dt = now if now.tzinfo else now.replace(tzinfo=UTC)
        last = _get_last_run(self.runtime, self.name)
        if last is None:
            return now_dt
        target = last + self.interval
        return target if target > now_dt else now_dt

    def run(self, now: datetime) -> None:
        _record_job_run(self.runtime, self.name, now)
        db = self.runtime.office.db
        sources = db.list_news_sources()
        for src in sources:
            if not src["enabled"]:
                continue
            src_id = src["id"]
            provider = src["provider"]
            name = src["name"]
            url = src["url"]
            count = 0
            try:
                if provider == "rss":
                    from data.providers.rss_news import RSSNewsProvider
                    rss_prov = RSSNewsProvider(url=url, name=name)
                    items = rss_prov.fetch_news()
                    for item in items:
                        # Deterministic ticker extraction from headline/summary
                        tickers = []
                        for word in item.headline.split() + (item.summary.split() if item.summary else []):
                            clean = word.strip(".,!?()[]{}\"':;").upper()
                            if len(clean) >= 2 and clean.isupper() and clean.isalpha():
                                tickers.append(clean)
                        # Check watchlist / portfolio / securities
                        db.insert_news(
                            headline=item.headline,
                            summary=item.summary,
                            full_text=item.full_text,
                            url=item.url,
                            source_id=src_id,
                            source=name,
                            provider="rss",
                            published_ts=item.published_at.isoformat(),
                            tickers=list(set(tickers))[:5],
                        )
                        count += 1
                elif provider == "alpaca":
                    # Use alpaca provider if available
                    env = self.runtime.office.get_env()
                    if hasattr(env, "market_data") and hasattr(env.market_data, "news"):
                        # or direct client
                        pass
                elif provider == "openbb":
                    from data.providers.openbb import OpenBBProvider
                    try:
                        obb_prov = OpenBBProvider()
                        items = obb_prov.get_news()
                        for item in items:
                            db.insert_news(
                                headline=item["headline"],
                                summary=item.summary,
                                full_text=None,
                                url=item["url"],
                                source_id=src_id,
                                source=name,
                                provider="openbb",
                                published_ts=item["published_at"].isoformat(),
                            )
                            count += 1
                    except Exception as e:
                        db.update_news_source_status(src_id, "unavailable", str(e))
                        continue

                db.update_news_source_status(src_id, "ok", None, now.isoformat())
                if count > 0 and self.runtime.event_log:
                    with db.transaction():
                        self.runtime.event_log.append(
                            "news.ingested", f"source:{src_id}",
                            {"source_id": src_id, "count": count},
                            actor="scheduler",
                        )
            except Exception as exc:
                logger.exception("Error ingesting from source %s: %s", name, exc)
                db.update_news_source_status(src_id, "error", str(exc))


class RetentionJob(Job):
    """Weekly DB retention cleanup and vacuum followed by size check."""

    name = "retention"

    def __init__(self, runtime: Runtime, interval_days: float = 7.0) -> None:
        self.runtime = runtime
        self.interval = timedelta(days=interval_days)

    def next_run(self, now: datetime) -> datetime | None:
        now_dt = now if now.tzinfo else now.replace(tzinfo=UTC)
        last = _get_last_run(self.runtime, self.name)
        if last is None:
            return now_dt + self.interval
        target = last + self.interval
        return target if target > now_dt else now_dt

    def run(self, now: datetime) -> None:
        _record_job_run(self.runtime, self.name, now)
        try:
            self.runtime.office.run_retention()
            self.runtime.office.check_db_size()
        except Exception:
            logger.exception("Error executing RetentionJob")


class MarketAnalystFixedJob(Job):
    """Fixed pre-market and macro event activations for Market Analyst."""

    name = "market_analyst_fixed"

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def next_run(self, now: datetime) -> datetime | None:
        try:
            now_dt = now if now.tzinfo else now.replace(tzinfo=UTC)
            today = now_dt.date()
            premkt_str = getattr(self.runtime.office.settings.schedule, "premarket_open", "09:00")
            try:
                hour_str, min_str = premkt_str.split(":")
                premkt_hour, premkt_min = int(hour_str), int(min_str)
            except Exception:
                premkt_hour, premkt_min = 9, 0

            today_premkt = datetime.combine(today, datetime.min.time(), tzinfo=UTC).replace(
                hour=premkt_hour, minute=premkt_min
            )
            if now_dt < today_premkt and today.weekday() < 5:
                return today_premkt

            from workflows.scheduling import _add_trading_days

            cal = getattr(self.runtime.office.get_env(), "calendar", None)
            next_tday = _add_trading_days(today, 1, cal)
            next_premkt = datetime.combine(next_tday, datetime.min.time(), tzinfo=UTC).replace(
                hour=premkt_hour, minute=premkt_min
            )
            return next_premkt
        except Exception:
            return (now if now.tzinfo else now.replace(tzinfo=UTC)) + timedelta(minutes=30)

    def run(self, now: datetime) -> None:
        _record_job_run(self.runtime, self.name, now)
        try:
            self.runtime.office.ensure_fixed_market_analyst_activations()
        except Exception:
            logger.exception("Error executing MarketAnalystFixedJob")


class ExpirePendingOrdersJob(Job):
    """Expire pending orders at their deadline or end of session."""

    name = "expire_pending"

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def next_run(self, now: datetime) -> datetime | None:
        rows = self.runtime.office.db.connection.execute(
            "SELECT id, draft_json, created_ts FROM orders WHERE approval_status = 'pending'"
        ).fetchall()
        if not rows:
            return None

        earliest: datetime | None = None
        for row in rows:
            draft = json.loads(row["draft_json"]) if row["draft_json"] else {}
            exp_str = draft.get("expires_at")
            if exp_str:
                try:
                    exp_dt = datetime.fromisoformat(str(exp_str).replace("Z", "+00:00"))
                    exp_dt = exp_dt if exp_dt.tzinfo else exp_dt.replace(tzinfo=UTC)
                    if earliest is None or exp_dt < earliest:
                        earliest = exp_dt
                except Exception:
                    pass

        if earliest is not None:
            return earliest

        now_dt = now if now.tzinfo else now.replace(tzinfo=UTC)
        today_close = now_dt.replace(hour=20, minute=0, second=0, microsecond=0)
        if now_dt < today_close:
            return today_close
        return today_close + timedelta(days=1)

    def run(self, now: datetime) -> None:
        _record_job_run(self.runtime, self.name, now)
        try:
            self.runtime.office.order_flow.expire_pending()
        except Exception:
            logger.exception("Error executing ExpirePendingOrdersJob")


class ReleaseQueuedOrdersJob(Job):
    """Release queued orders when market opens."""

    name = "release_queued"

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def next_run(self, now: datetime) -> datetime | None:
        row = self.runtime.office.db.connection.execute(
            "SELECT id FROM orders WHERE status = 'queued' LIMIT 1"
        ).fetchone()
        if not row:
            return None

        broker = self.runtime.office.order_flow.broker
        if hasattr(broker, "next_market_open"):
            nxt = broker.next_market_open(now)
            if isinstance(nxt, datetime):
                return nxt if nxt.tzinfo else nxt.replace(tzinfo=UTC)

        if hasattr(broker, "_client") and hasattr(broker._client, "get_clock"):
            try:
                clk = broker._client.get_clock()
                nxt = getattr(clk, "next_open", None)
                if nxt:
                    if isinstance(nxt, datetime):
                        return nxt if nxt.tzinfo else nxt.replace(tzinfo=UTC)
                    return datetime.fromisoformat(str(nxt).replace("Z", "+00:00"))
            except Exception:
                pass

        now_dt = now if now.tzinfo else now.replace(tzinfo=UTC)
        target = now_dt.replace(hour=13, minute=30, second=0, microsecond=0)
        if target <= now_dt:
            target += timedelta(days=1)
        while target.weekday() >= 5:
            target += timedelta(days=1)
        return target

    def run(self, now: datetime) -> None:
        _record_job_run(self.runtime, self.name, now)
        try:
            self.runtime.office.order_flow.release_queued()
        except Exception:
            logger.exception("Error executing ReleaseQueuedOrdersJob")
