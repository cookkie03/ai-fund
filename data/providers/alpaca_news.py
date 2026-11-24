"""Normalize Alpaca news without inferring sentiment from headlines."""

from dataclasses import dataclass
from datetime import datetime

from alpaca.data.requests import NewsRequest


@dataclass(frozen=True)
class NewsItem:
    headline: str
    source: str
    url: str
    published_at: datetime


class AlpacaNewsProvider:
    def __init__(self, client):
        self._client = client

    def get_news(self, symbol: str, start: datetime, end: datetime, limit: int = 200) -> tuple[NewsItem, ...]:
        if (
            not symbol.strip()
            or start.utcoffset() is None
            or end.utcoffset() is None
            or start >= end
        ):
            raise ValueError("news query requires a symbol and ordered timezone-aware bounds")
        
        all_news = []
        page_token = None
        while len(all_news) < limit:
            req_limit = min(50, limit - len(all_news))
            try:
                req = NewsRequest(symbols=symbol, start=start, end=end, limit=req_limit, page_token=page_token)
            except TypeError:
                req = NewsRequest(symbols=symbol, start=start, end=end, limit=req_limit)
            
            try:
                response = self._client.get_news(req)
            except Exception:
                break
            
            news_batch = response.data.get("news", []) if hasattr(response, "data") else getattr(response, "news", [])
            if not news_batch:
                break
            
            for item in news_batch:
                symbols = getattr(item, "symbols", [])
                if (
                    item.url
                    and item.headline
                    and item.source
                    and item.created_at.utcoffset() is not None
                    and symbol.upper() in (name.upper() for name in symbols)
                    and start <= item.created_at < end
                ):
                    all_news.append(
                        NewsItem(item.headline, item.source, item.url, item.created_at)
                    )
            
            page_token = getattr(response, "next_page_token", None) or (response.data.get("next_page_token") if hasattr(response, "data") else None)
            if not page_token or len(news_batch) < req_limit:
                break
                
        return tuple(all_news)
