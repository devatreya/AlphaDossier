"""Persistence for sources, chunks, and their embeddings.

All writes go through asyncpg connections acquired from `db.acquire()`. The
pool's `init` callback registers the pgvector codec so embeddings round-trip
as Python lists/numpy arrays without manual string formatting.

Reads return typed Pydantic models (`StoredSource`, `StoredChunk`) with
`metadata` always normalised to a `dict`, regardless of whether asyncpg
returned the underlying jsonb column as a dict or a raw string.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence
from uuid import UUID

import asyncpg

from ..data._types import RawDocument
from ..db import acquire
from ._types import Chunk, StoredChunk, StoredSource

# Schema reference: db/migrations/001_init.sql

_INSERT_SOURCE_SQL = """
    insert into sources
        (thesis_id, kind, provider, url, title, published_at, raw_path, content_hash, metadata)
    values
        ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
    returning id
"""

_INSERT_CHUNK_SQL = """
    insert into chunks
        (source_id, chunk_index, text, embedding, token_count, metadata)
    values
        ($1, $2, $3, $4, $5, $6::jsonb)
    returning id
"""

_SELECT_SOURCE_SQL = """
    select id, thesis_id, kind, provider, url, title, published_at, fetched_at,
           raw_path, content_hash, metadata
    from sources
    where id = $1
"""

# Embedding intentionally omitted — see StoredChunk docstring.
_SELECT_CHUNKS_FOR_SOURCE_SQL = """
    select id, source_id, chunk_index, text, token_count, metadata
    from chunks
    where source_id = $1
    order by chunk_index asc
"""


def _to_jsonb(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {})


def decode_jsonb(value: Any) -> dict[str, Any]:
    """Coerce a jsonb column value to a Python dict.

    asyncpg returns jsonb as `dict` when its codec is registered (the default)
    but as `str` if it isn't. Both shapes can also leak through depending on
    pool init ordering. This helper makes reads stable regardless.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _source_from_record(row: Mapping[str, Any]) -> StoredSource:
    return StoredSource(
        id=row["id"],
        thesis_id=row["thesis_id"],
        kind=row["kind"],
        provider=row["provider"],
        url=row["url"],
        title=row["title"],
        published_at=row["published_at"],
        fetched_at=row["fetched_at"],
        raw_path=row["raw_path"],
        content_hash=row["content_hash"],
        metadata=decode_jsonb(row["metadata"]),
    )


def _chunk_from_record(row: Mapping[str, Any]) -> StoredChunk:
    return StoredChunk(
        id=row["id"],
        source_id=row["source_id"],
        chunk_index=row["chunk_index"],
        text=row["text"],
        token_count=row["token_count"],
        metadata=decode_jsonb(row["metadata"]),
    )


async def insert_source(
    thesis_id: UUID,
    doc: RawDocument,
    *,
    raw_path: str | None = None,
    conn: asyncpg.Connection | None = None,
) -> UUID:
    """Persist a RawDocument. Returns the new source row id.

    `raw_path` is an optional pointer (e.g. S3 key) to the bytes — leave None
    for now; Phase 3 only stores extracted text via `chunks`.
    """
    args = (
        thesis_id,
        doc.kind,
        doc.provider,
        doc.url,
        doc.title,
        doc.published_at,
        raw_path,
        doc.content_hash,
        _to_jsonb(doc.metadata),
    )
    if conn is not None:
        return await conn.fetchval(_INSERT_SOURCE_SQL, *args)
    async with acquire() as c:
        return await c.fetchval(_INSERT_SOURCE_SQL, *args)


async def insert_chunks(
    source_id: UUID,
    chunks: Sequence[Chunk],
    embeddings: Sequence[Sequence[float]],
    *,
    conn: asyncpg.Connection | None = None,
) -> list[UUID]:
    """Insert chunks with their pre-computed embeddings.

    `chunks` and `embeddings` must be aligned and the same length. Returns the
    new chunk row ids in the same order.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks/embeddings length mismatch: {len(chunks)} vs {len(embeddings)}"
        )
    if not chunks:
        return []

    rows: list[UUID] = []

    async def do_insert(c: asyncpg.Connection) -> None:
        async with c.transaction():
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                row_id = await c.fetchval(
                    _INSERT_CHUNK_SQL,
                    source_id,
                    chunk.chunk_index,
                    chunk.text,
                    list(embedding),
                    chunk.token_count,
                    _to_jsonb(chunk.metadata),
                )
                rows.append(row_id)

    if conn is not None:
        await do_insert(conn)
    else:
        async with acquire() as c:
            await do_insert(c)
    return rows


async def get_source(
    source_id: UUID, *, conn: asyncpg.Connection | None = None
) -> StoredSource | None:
    if conn is not None:
        row = await conn.fetchrow(_SELECT_SOURCE_SQL, source_id)
    else:
        async with acquire() as c:
            row = await c.fetchrow(_SELECT_SOURCE_SQL, source_id)
    return _source_from_record(row) if row is not None else None


async def get_chunks_for_source(
    source_id: UUID, *, conn: asyncpg.Connection | None = None
) -> list[StoredChunk]:
    if conn is not None:
        rows = await conn.fetch(_SELECT_CHUNKS_FOR_SOURCE_SQL, source_id)
    else:
        async with acquire() as c:
            rows = await c.fetch(_SELECT_CHUNKS_FOR_SOURCE_SQL, source_id)
    return [_chunk_from_record(r) for r in rows]
