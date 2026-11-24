"""Robust RSS/Atom feed parser using httpx and stdlib xml.etree.ElementTree."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RSSItem:
    headline: str
    summary: str | None
    url: str
    published_at: datetime
    source: str
    image_url: str | None = None
    full_text: str | None = None


class RSSNewsProvider:
    def __init__(self, url: str, name: str, timeout: float = 10.0, max_size_bytes: int = 2 * 1024 * 1024) -> None:
        self.url = url
        self.name = name
        self.timeout = timeout
        self.max_size_bytes = max_size_bytes

    def fetch_news(self) -> tuple[RSSItem, ...]:
        if not self.url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid RSS URL scheme: {self.url}")

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(self.url)
                response.raise_for_status()
                if len(response.content) > self.max_size_bytes:
                    raise ValueError("Feed content exceeds maximum size limit")
                content = response.content
        except Exception as exc:
            logger.error("Failed to fetch RSS feed %s (%s): %s", self.name, self.url, exc)
            raise

        items: list[RSSItem] = []
        try:
            root = ET.fromstring(content)
        except Exception as exc:
            logger.error("Failed to parse XML for feed %s: %s", self.name, exc)
            raise ValueError(f"Invalid XML: {exc}") from exc

        # Check RSS 2.0 (<rss><channel><item>...</item></channel></rss>)
        channel = root.find("channel")
        if channel is not None:
            for node in channel.findall("item"):
                title = node.findtext("title")
                link = node.findtext("link")
                desc = node.findtext("description")
                pub_date_str = node.findtext("pubDate")

                # Try parsing pubDate
                pub_at = datetime.now(UTC)
                if pub_date_str:
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(pub_date_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=UTC)
                        pub_at = dt.astimezone(UTC)
                    except Exception:
                        pass

                if title and link:
                    items.append(
                        RSSItem(
                            headline=title.strip(),
                            summary=desc.strip() if desc else None,
                            url=link.strip(),
                            published_at=pub_at,
                            source=self.name,
                        )
                    )
        else:
            # Check Atom feed (<feed><entry>...</entry></feed>)
            # Handle default namespace if present
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns) or root.findall("entry")
            for node in entries:
                title = node.findtext("atom:title", namespaces=ns) or node.findtext("title")
                link_node = node.find("atom:link", namespaces=ns) or node.find("link")
                link = link_node.get("href") if link_node is not None else node.findtext("link")
                summary = node.findtext("atom:summary", namespaces=ns) or node.findtext("summary") or node.findtext("atom:content", namespaces=ns)
                updated_str = node.findtext("atom:updated", namespaces=ns) or node.findtext("updated") or node.findtext("atom:published", namespaces=ns)

                pub_at = datetime.now(UTC)
                if updated_str:
                    try:
                        dt = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=UTC)
                        pub_at = dt.astimezone(UTC)
                    except Exception:
                        pass

                if title and link:
                    items.append(
                        RSSItem(
                            headline=title.strip(),
                            summary=summary.strip() if summary else None,
                            url=link.strip(),
                            published_at=pub_at,
                            source=self.name,
                        )
                    )

        return tuple(items)
