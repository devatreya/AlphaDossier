"""Voyage AI embeddings client.

Docs: https://docs.voyageai.com/reference/embeddings-api

`voyage-finance-2` returns 1024-dim vectors. The DB schema's `chunks.embedding`
column is fixed at vector(1024) — switching providers means a migration.

Voyage's `input_type` parameter changes how the model processes text:
  * "document"  → ingestion (asymmetric retrieval setup)
  * "query"     → search query (matched against document embeddings)

Use the matching kind on each side; mixing them silently degrades recall.
"""
from __future__ import annotations

import asyncio

import httpx

from ..config import get_settings
from ..data._errors import ConnectorError, MissingApiKeyError
from ..data._http import make_client, request_json

PROVIDER = "voyage"
EMBED_URL = "https://api.voyageai.com/v1/embeddings"

# Voyage caps batch size; 128 is well within the documented limit and keeps
# request bodies under typical proxy size limits.
MAX_BATCH_SIZE = 128


def _check_provider() -> None:
    settings = get_settings()
    if settings.embedding_provider.lower() != "voyage":
        raise NotImplementedError(
            f"embedding_provider={settings.embedding_provider!r} not supported in Phase 3; "
            "only 'voyage' is wired up."
        )
    if not settings.voyage_api_key:
        raise MissingApiKeyError("VOYAGE_API_KEY", provider=PROVIDER)


async def _embed_batch(
    texts: list[str], *, input_type: str, client: httpx.AsyncClient
) -> list[list[float]]:
    settings = get_settings()
    payload = {
        "input": texts,
        "model": settings.voyage_embedding_model,
        "input_type": input_type,
    }
    headers = {
        "Authorization": f"Bearer {settings.voyage_api_key}",
        "Content-Type": "application/json",
    }
    body = await request_json(
        client, "POST", EMBED_URL,
        json_body=payload, headers=headers, provider=PROVIDER,
    )
    data = body.get("data") or []
    # Voyage returns embeddings already aligned by `index` but we sort defensively.
    data_sorted = sorted(data, key=lambda d: d.get("index", 0))
    if len(data_sorted) != len(texts):
        raise ConnectorError(
            f"voyage: returned {len(data_sorted)} embeddings for {len(texts)} inputs",
            provider=PROVIDER,
        )
    return [list(item["embedding"]) for item in data_sorted]


async def _embed(
    texts: list[str],
    *,
    input_type: str,
    client: httpx.AsyncClient | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    _check_provider()
    owned = client is None
    c = client or make_client()
    try:
        if len(texts) <= MAX_BATCH_SIZE:
            return await _embed_batch(texts, input_type=input_type, client=c)
        # Run batches sequentially. Parallelising hits Voyage rate limits faster
        # than it shaves wall-clock for the document sizes we expect.
        out: list[list[float]] = []
        for i in range(0, len(texts), MAX_BATCH_SIZE):
            batch = texts[i : i + MAX_BATCH_SIZE]
            out.extend(await _embed_batch(batch, input_type=input_type, client=c))
        return out
    finally:
        if owned:
            await c.aclose()


async def embed_documents(
    texts: list[str], *, client: httpx.AsyncClient | None = None
) -> list[list[float]]:
    """Embed chunk text for storage. Uses input_type='document'."""
    return await _embed(texts, input_type="document", client=client)


async def embed_query(
    text: str, *, client: httpx.AsyncClient | None = None
) -> list[float]:
    """Embed a retrieval query. Uses input_type='query'."""
    embeddings = await _embed([text], input_type="query", client=client)
    return embeddings[0]


async def embed_documents_concurrent(
    texts: list[str],
    *,
    concurrency: int = 2,
    client: httpx.AsyncClient | None = None,
) -> list[list[float]]:
    """Embed many chunks with bounded concurrency.

    Useful for ingesting a single large document where waiting for serial batches
    is the bottleneck. Default concurrency=2 stays well under Voyage's free-tier
    limits; bump cautiously.
    """
    if not texts:
        return []
    _check_provider()
    owned = client is None
    c = client or make_client()
    sem = asyncio.Semaphore(concurrency)

    async def run_batch(batch: list[str]) -> list[list[float]]:
        async with sem:
            return await _embed_batch(batch, input_type="document", client=c)

    try:
        batches = [
            texts[i : i + MAX_BATCH_SIZE]
            for i in range(0, len(texts), MAX_BATCH_SIZE)
        ]
        results = await asyncio.gather(*(run_batch(b) for b in batches))
    finally:
        if owned:
            await c.aclose()
    return [vec for batch in results for vec in batch]
