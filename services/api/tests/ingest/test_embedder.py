from __future__ import annotations

import httpx
import pytest

from services.api import config
from services.api.data._errors import ConnectorError, MissingApiKeyError
from services.api.ingest import embedder

from ..data.conftest import make_mock_client


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    config.get_settings.cache_clear()


def _embed_payload(n: int, dims: int = 4) -> dict:
    return {
        "model": "voyage-finance-2",
        "data": [
            {"index": i, "embedding": [float(i + 1) * 0.1] * dims}
            for i in range(n)
        ],
        "usage": {"total_tokens": 100},
    }


async def test_embed_documents_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "k")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_embed_payload(2))

    async with make_mock_client(handler) as client:
        vectors = await embedder.embed_documents(["chunk a", "chunk b"], client=client)

    assert len(vectors) == 2
    assert vectors[0] == [0.1, 0.1, 0.1, 0.1]
    assert captured["auth"] == "Bearer k"
    body = captured["body"].decode()
    assert '"input_type":"document"' in body or '"input_type": "document"' in body


async def test_embed_query_uses_query_input_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "k")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read().decode()
        return httpx.Response(200, json=_embed_payload(1))

    async with make_mock_client(handler) as client:
        vec = await embedder.embed_query("a question", client=client)

    assert len(vec) == 4
    assert "input_type" in captured["body"]
    assert "query" in captured["body"]


async def test_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError):
        await embedder.embed_documents(["x"])


async def test_unsupported_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("VOYAGE_API_KEY", "k")
    with pytest.raises(NotImplementedError):
        await embedder.embed_documents(["x"])


async def test_batches_large_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "k")
    monkeypatch.setattr(embedder, "MAX_BATCH_SIZE", 3)

    request_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        request_count["n"] += 1
        body = request.read().decode()
        # Count inputs by counting commas + 1 within "input": [...]
        import json

        data = json.loads(body)
        return httpx.Response(200, json=_embed_payload(len(data["input"])))

    async with make_mock_client(handler) as client:
        vectors = await embedder.embed_documents(["a"] * 7, client=client)

    assert len(vectors) == 7
    # ceil(7/3) = 3 requests
    assert request_count["n"] == 3


async def test_embedding_count_mismatch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_embed_payload(1))  # but we sent 2

    async with make_mock_client(handler) as client:
        with pytest.raises(ConnectorError, match="returned 1 embeddings for 2"):
            await embedder.embed_documents(["a", "b"], client=client)


async def test_empty_input_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    # No key set, but no inputs => no error, no request.
    assert await embedder.embed_documents([]) == []
