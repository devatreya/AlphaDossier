from __future__ import annotations

from uuid import uuid4

import pytest

from services.api.ingest import retriever

from .conftest import FakeConn, find_call


async def test_search_uses_provided_embedding_and_skips_voyage() -> None:
    conn = FakeConn()
    cid, sid = uuid4(), uuid4()
    conn.fetch_results = [[
        {
            "chunk_id": cid,
            "source_id": sid,
            "text": "the answer",
            "chunk_index": 0,
            "chunk_metadata": {},
            "source_kind": "news",
            "source_provider": "news_api",
            "source_url": "https://x",
            "source_title": "title",
            "similarity": 0.91,
        }
    ]]

    results = await retriever.search(
        "what is the answer",
        embedding=[0.1] * 1024,
        top_k=5,
        conn=conn,
    )

    assert len(results) == 1
    r = results[0]
    assert r.chunk_id == cid
    assert r.similarity == pytest.approx(0.91)
    assert r.source_kind == "news"
    sql, args = find_call(conn, method="fetch", contains="<=>")
    assert args[0] == [0.1] * 1024
    assert args[3] == 5  # top_k


async def test_search_filters_by_thesis_and_kind() -> None:
    conn = FakeConn()
    conn.fetch_results = [[]]
    thesis_id = uuid4()

    await retriever.search(
        "q",
        thesis_id=thesis_id,
        source_kinds=["sec_10k", "sec_8k"],
        embedding=[0.0] * 1024,
        conn=conn,
    )
    sql, args = find_call(conn, method="fetch", contains="<=>")
    assert args[1] == thesis_id
    assert args[2] == ["sec_10k", "sec_8k"]


async def test_search_decodes_jsonb_string_metadata() -> None:
    """If pgvector codec is registered but the jsonb codec isn't, asyncpg can
    return jsonb columns as raw strings — the retriever should JSON-decode them."""
    conn = FakeConn()
    conn.fetch_results = [[
        {
            "chunk_id": uuid4(),
            "source_id": uuid4(),
            "text": "x",
            "chunk_index": 0,
            "chunk_metadata": '{"a": 1}',  # jsonb-as-string
            "source_kind": None,
            "source_provider": None,
            "source_url": None,
            "source_title": None,
            "similarity": 0.5,
        }
    ]]
    [r] = await retriever.search("q", embedding=[0.1] * 1024, conn=conn)
    assert r.metadata == {"a": 1}
