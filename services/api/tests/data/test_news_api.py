from __future__ import annotations

from datetime import date

import httpx
import pytest

from services.api.data import news_api
from services.api.data._errors import MissingApiKeyError

from .conftest import make_mock_client


def _ok_payload() -> dict:
    return {
        "status": "ok",
        "totalResults": 1,
        "articles": [
            {
                "source": {"id": "reuters", "name": "Reuters"},
                "author": "Jane Reporter",
                "title": "Acme posts strong Q3",
                "description": "Acme beat estimates...",
                "url": "https://example.com/a",
                "publishedAt": "2026-04-15T08:30:00Z",
                "content": "Full body...",
            }
        ],
    }


async def test_search_everything_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWS_API_KEY", "test-key")

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key_header"] = request.headers.get("X-Api-Key")
        return httpx.Response(200, json=_ok_payload())

    async with make_mock_client(handler) as client:
        docs = await news_api.search_everything(
            "Acme",
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            page_size=5,
            client=client,
        )

    assert "newsapi.org/v2/everything" in captured["url"]
    assert captured["api_key_header"] == "test-key"
    assert "from=2026-04-01" in captured["url"]
    assert len(docs) == 1
    doc = docs[0]
    assert doc.kind == "news"
    assert doc.title == "Acme posts strong Q3"
    assert doc.published_at is not None
    assert "Acme beat estimates" in doc.text
    assert doc.metadata["source"] == "Reuters"


async def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWS_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError) as exc:
        await news_api.search_everything("Acme")
    assert exc.value.env_var == "NEWS_API_KEY"
    assert exc.value.provider == "news_api"


async def test_clamps_page_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWS_API_KEY", "k")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"articles": []})

    async with make_mock_client(handler) as client:
        await news_api.search_everything("q", page_size=999, client=client)
    assert "pageSize=100" in captured["url"]
