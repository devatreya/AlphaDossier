"""Vector retrieval over chunks via pgvector cosine distance.

Workflow:
  1. Embed query with Voyage (input_type='query').
  2. Run `embedding <=> $1` (cosine distance, <=> operator) over `chunks`.
  3. Join `sources` so retrievals carry kind/url/title for downstream citation.

The migration creates an IVFFlat cosine index on `chunks.embedding`. Recall
improves with more lists; for the demo dataset 100 lists is plenty.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
import httpx

from ..db import acquire
from . import embedder
from ._types import Retrieval
from .document_store import decode_jsonb

_SEARCH_SQL = """
    select
        c.id          as chunk_id,
        c.source_id   as source_id,
        c.text        as text,
        c.chunk_index as chunk_index,
        c.metadata    as chunk_metadata,
        s.kind        as source_kind,
        s.provider    as source_provider,
        s.url         as source_url,
        s.title       as source_title,
        1 - (c.embedding <=> $1) as similarity
    from chunks c
    join sources s on s.id = c.source_id
    where ($2::uuid is null or s.thesis_id = $2)
      and ($3::text[] is null or s.kind = any($3))
    order by c.embedding <=> $1
    limit $4
"""


def _record_to_retrieval(row: asyncpg.Record) -> Retrieval:
    return Retrieval(
        chunk_id=row["chunk_id"],
        source_id=row["source_id"],
        text=row["text"],
        chunk_index=row["chunk_index"],
        similarity=float(row["similarity"]),
        source_kind=row["source_kind"],
        source_provider=row["source_provider"],
        source_url=row["source_url"],
        source_title=row["source_title"],
        metadata=decode_jsonb(row["chunk_metadata"]),
    )


async def search(
    query: str,
    *,
    thesis_id: UUID | None = None,
    source_kinds: list[str] | None = None,
    top_k: int = 12,
    conn: asyncpg.Connection | None = None,
    embed_client: httpx.AsyncClient | None = None,
    embedding: list[float] | None = None,
) -> list[Retrieval]:
    """Retrieve top-k chunks for `query`, optionally scoped to one thesis or
    a subset of source kinds (e.g. ['sec_10k', 'sec_8k']).

    Pass `embedding` to skip the embed step (useful when the caller already
    embedded the query for another search).
    """
    vector = embedding if embedding is not None else await embedder.embed_query(
        query, client=embed_client
    )

    args: tuple[Any, ...] = (vector, thesis_id, source_kinds, top_k)

    if conn is not None:
        rows = await conn.fetch(_SEARCH_SQL, *args)
    else:
        async with acquire() as c:
            rows = await c.fetch(_SEARCH_SQL, *args)
    return [_record_to_retrieval(r) for r in rows]
