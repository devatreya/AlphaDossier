from __future__ import annotations

import httpx
import pytest

from services.api.data import uk_rns

from .conftest import make_mock_client


async def test_search_rns_proxies_news_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWS_API_KEY", "k")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "articles": [
                    {
                        "source": {"id": "investegate", "name": "Investegate"},
                        "title": "Shell plc - Q3 Trading update",
                        "description": "Results released",
                        "url": "https://investegate.example/shell-q3",
                        "publishedAt": "2026-04-15T07:00:00Z",
                    }
                ]
            },
        )

    async with make_mock_client(handler) as client:
        docs = await uk_rns.search_rns(
            "SHEL.L", company_name="Shell plc", client=client
        )

    assert "investegate.co.uk" in captured["url"]
    assert "%22SHEL%22" in captured["url"] or "SHEL" in captured["url"]
    assert len(docs) == 1
    assert docs[0].kind == "rns_proxy"
    assert docs[0].provider == "uk_rns_proxy"
    assert "RNS proxy" in docs[0].metadata["note"]
