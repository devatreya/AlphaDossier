"""NewsAPI.org connector.

Docs: https://newsapi.org/docs/endpoints

We use /v2/everything for breadth (search across all indexed sources). Free
tier limits free requests and excludes articles older than ~30 days, which
matches our recent-news use case for Phase 4.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

import httpx

from ..config import get_settings
from ._errors import MissingApiKeyError
from ._http import make_client, request_json
from ._types import RawDocument

PROVIDER = "news_api"
BASE_URL = "https://newsapi.org/v2"


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    # NewsAPI returns ISO 8601 with trailing Z.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def _article_to_document(article: dict) -> RawDocument:
    title = article.get("title")
    description = article.get("description") or ""
    content = article.get("content") or ""
    text_parts = [p for p in (title, description, content) if p]
    return RawDocument(
        kind="news",
        provider=PROVIDER,
        url=article.get("url"),
        title=title,
        published_at=_parse_published_at(article.get("publishedAt")),
        text="\n\n".join(text_parts),
        metadata={
            "source": (article.get("source") or {}).get("name"),
            "author": article.get("author"),
        },
    )


async def search_everything(
    query: str,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    language: str = "en",
    sort_by: str = "publishedAt",
    page_size: int = 20,
    domains: Iterable[str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[RawDocument]:
    """Search NewsAPI /v2/everything. Returns up to page_size articles as RawDocuments.

    Raises MissingApiKeyError if NEWS_API_KEY is unset.
    """
    settings = get_settings()
    if not settings.news_api_key:
        raise MissingApiKeyError("NEWS_API_KEY", provider=PROVIDER)

    params: dict[str, str | int] = {
        "q": query,
        "language": language,
        "sortBy": sort_by,
        "pageSize": min(max(page_size, 1), 100),
    }
    if from_date:
        params["from"] = from_date.isoformat()
    if to_date:
        params["to"] = to_date.isoformat()
    if domains:
        params["domains"] = ",".join(domains)

    headers = {"X-Api-Key": settings.news_api_key}

    owned = client is None
    c = client or make_client()
    try:
        payload = await request_json(
            c, "GET", f"{BASE_URL}/everything",
            params=params, headers=headers, provider=PROVIDER,
        )
    finally:
        if owned:
            await c.aclose()

    articles = payload.get("articles") or []
    return [_article_to_document(a) for a in articles]
