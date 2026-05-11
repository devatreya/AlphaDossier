from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from services.api.data._types import RawDocument
from services.api.ingest import document_store
from services.api.ingest._types import Chunk

from .conftest import FakeConn, find_call


def _doc() -> RawDocument:
    return RawDocument(
        kind="news",
        provider="news_api",
        url="https://x/y",
        title="Acme Q3",
        published_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
        text="body",
        content_hash="abc123",
        metadata={"author": "Reuters"},
    )


async def test_insert_source_executes_insert() -> None:
    conn = FakeConn()
    new_id = uuid4()
    conn.fetchval_results = [new_id]
    thesis_id = uuid4()

    out = await document_store.insert_source(thesis_id, _doc(), conn=conn)

    assert out == new_id
    sql, args = find_call(conn, method="fetchval", contains="insert into sources")
    assert args[0] == thesis_id
    assert args[1] == "news"
    assert args[2] == "news_api"
    assert args[7] == "abc123"
    # metadata serialised as JSON string for jsonb cast
    assert args[8] == json.dumps({"author": "Reuters"})


async def test_insert_chunks_writes_each_with_embedding() -> None:
    conn = FakeConn()
    chunk_ids = [uuid4(), uuid4()]
    conn.fetchval_results = chunk_ids[:]
    source_id = uuid4()

    chunks = [
        Chunk(text="alpha", chunk_index=0, token_count=2, metadata={"a": 1}),
        Chunk(text="beta", chunk_index=1, token_count=2, metadata={}),
    ]
    embeddings = [[0.1, 0.2], [0.3, 0.4]]

    out = await document_store.insert_chunks(
        source_id, chunks, embeddings, conn=conn
    )

    assert out == chunk_ids
    inserts = [c for c in conn.calls if c[0] == "fetchval"]
    assert len(inserts) == 2
    _method, sql, first_args = inserts[0]
    assert "insert into chunks" in sql
    assert first_args[0] == source_id
    assert first_args[1] == 0
    assert first_args[2] == "alpha"
    assert first_args[3] == [0.1, 0.2]
    # transaction was opened
    assert any(c[0] == "transaction_enter" for c in conn.calls)
    assert any(c[0] == "transaction_commit" for c in conn.calls)


async def test_insert_chunks_length_mismatch() -> None:
    conn = FakeConn()
    with pytest.raises(ValueError, match="length mismatch"):
        await document_store.insert_chunks(
            uuid4(),
            [Chunk(text="a", chunk_index=0, token_count=1)],
            [[0.1], [0.2]],
            conn=conn,
        )


async def test_insert_chunks_empty_returns_empty() -> None:
    conn = FakeConn()
    out = await document_store.insert_chunks(uuid4(), [], [], conn=conn)
    assert out == []
    # No SQL calls made.
    assert all(c[0].startswith("transaction") is False for c in conn.calls) or conn.calls == []


async def test_get_source_returns_typed_row_with_normalised_metadata() -> None:
    conn = FakeConn()
    sid = uuid4()
    fetched_at = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    # asyncpg returns jsonb as a string when its codec isn't registered — the
    # store must normalise that to a dict so callers see a consistent shape.
    conn.fetchrow_results = [{
        "id": sid,
        "thesis_id": None,
        "kind": "news",
        "provider": "news_api",
        "url": "https://x",
        "title": "T",
        "published_at": None,
        "fetched_at": fetched_at,
        "raw_path": None,
        "content_hash": "abc",
        "metadata": '{"author": "Reuters"}',  # stringified jsonb
    }]
    src = await document_store.get_source(sid, conn=conn)
    assert src is not None
    assert src.id == sid
    assert src.kind == "news"
    assert src.metadata == {"author": "Reuters"}
    sql, args = find_call(conn, method="fetchrow", contains="from sources")
    assert args == (sid,)


async def test_get_source_returns_none_when_missing() -> None:
    conn = FakeConn()  # empty fetchrow_results -> None
    assert await document_store.get_source(uuid4(), conn=conn) is None


async def test_get_chunks_for_source_returns_typed_rows() -> None:
    conn = FakeConn()
    sid = uuid4()
    cid1, cid2 = uuid4(), uuid4()
    conn.fetch_results = [[
        {
            "id": cid1, "source_id": sid, "chunk_index": 0,
            "text": "a", "token_count": 1,
            "metadata": {"source_kind": "news"},
        },
        {
            "id": cid2, "source_id": sid, "chunk_index": 1,
            "text": "b", "token_count": 1,
            "metadata": '{"source_kind": "news"}',  # stringified
        },
    ]]
    rows = await document_store.get_chunks_for_source(sid, conn=conn)
    assert [r.chunk_index for r in rows] == [0, 1]
    assert all(isinstance(r.metadata, dict) for r in rows)
    assert rows[1].metadata == {"source_kind": "news"}
    sql, args = find_call(conn, method="fetch", contains="from chunks")
    assert "order by chunk_index" in sql
    # embedding column intentionally not selected
    assert "embedding" not in sql
    assert args == (sid,)


def test_decode_jsonb_handles_all_shapes() -> None:
    assert document_store.decode_jsonb(None) == {}
    assert document_store.decode_jsonb({"a": 1}) == {"a": 1}
    assert document_store.decode_jsonb('{"a": 1}') == {"a": 1}
    # Garbage strings degrade gracefully.
    assert document_store.decode_jsonb("not json") == {}
    # Non-object JSON also yields empty (we only accept object shape).
    assert document_store.decode_jsonb("[1,2,3]") == {}
