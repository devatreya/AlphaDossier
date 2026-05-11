"""Thesis HTTP API.

Endpoints:
  POST /thesis                       — create a thesis row (status=pending)
                                       and dispatch the orchestrator in the
                                       background. Returns 202 + thesis_id.
  GET  /thesis/{id}                  — read the thesis row + dossier
  GET  /thesis/{id}/citations        — list citations with supporting chunks
  GET  /thesis/{id}/audit            — list audit_log rows for the thesis

The orchestrator is dispatched via `asyncio.create_task` so the request returns
immediately. The frontend polls GET /thesis/{id} until status transitions to
'completed' or 'failed'. See jobs.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Coroutine
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..data import identifiers
from ..db import acquire, get_pool
from ..ingest.document_store import decode_jsonb
from ..jobs import get_thesis_dispatcher
from ..orchestrator import ThesisRunRequest
from ..schemas import (
    AuditEvent,
    AuditListResponse,
    ChunkSnippet,
    CitationListItem,
    CitationListResponse,
    ThesisCreateRequest,
    ThesisCreateResponse,
    ThesisGetResponse,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/thesis", tags=["thesis"])


# ---------- DB dependency ----------


async def get_db_conn() -> AsyncIterator[asyncpg.Connection]:
    """Yield a pooled connection. 503 if the pool isn't initialised."""
    if get_pool() is None:
        raise HTTPException(
            status_code=503, detail="database unavailable — set DATABASE_URL",
        )
    async with acquire() as conn:
        yield conn


# ---------- SQL ----------


_INSERT_PENDING_THESIS = """
    insert into theses (id, user_id, ticker, focus_question, status)
    values ($1, $2, $3, $4, 'pending')
    on conflict (id) do nothing
"""

_SELECT_THESIS = """
    select id, ticker, focus_question, status, research_stance,
           evidence_strength, summary, error, created_at, updated_at
    from theses
    where id = $1
"""

_SELECT_CITATIONS = """
    select id, section, claim, chunk_ids, confidence, created_at
    from citations
    where thesis_id = $1
    order by created_at asc
"""

_SELECT_CHUNKS_BY_IDS = """
    select c.id as chunk_id, c.source_id, c.text,
           s.kind as source_kind, s.provider as source_provider,
           s.url as source_url, s.title as source_title
    from chunks c
    join sources s on s.id = c.source_id
    where c.id = any($1::uuid[])
"""

_SELECT_AUDIT = """
    select id, actor, action, status, model, input_tokens, output_tokens,
           cost_usd, latency_ms, payload, created_at
    from audit_log
    where thesis_id = $1
    order by created_at desc
    limit $2
"""


# ---------- POST /thesis ----------


@router.post(
    "",
    response_model=ThesisCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_thesis(
    req: ThesisCreateRequest,
    conn: asyncpg.Connection = Depends(get_db_conn),
    dispatcher: Callable[[ThesisRunRequest], Awaitable[None]] = Depends(
        get_thesis_dispatcher
    ),
) -> ThesisCreateResponse:
    """Validate, create a pending thesis row, and schedule the orchestrator.

    Returns 202 immediately; the client polls `GET /thesis/{id}` for progress.
    """
    try:
        instrument = identifiers.resolve(req.ticker)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid ticker: {exc}"
        ) from exc

    thesis_id = uuid4()
    await conn.execute(
        _INSERT_PENDING_THESIS,
        thesis_id, None, instrument.ticker, req.focus_question,
    )

    run_req = ThesisRunRequest(
        thesis_id=thesis_id,
        ticker=instrument.ticker,
        focus_question=req.focus_question,
    )
    # Fire-and-forget. The dispatcher's coroutine handles its own errors.
    coro: Coroutine[Any, Any, None] = dispatcher(run_req)  # type: ignore[assignment]
    asyncio.create_task(coro)

    return ThesisCreateResponse(thesis_id=thesis_id, status="pending")


# ---------- GET /thesis/{id} ----------


@router.get("/{thesis_id}", response_model=ThesisGetResponse)
async def get_thesis(
    thesis_id: UUID,
    conn: asyncpg.Connection = Depends(get_db_conn),
) -> ThesisGetResponse:
    row = await conn.fetchrow(_SELECT_THESIS, thesis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="thesis not found")
    summary = decode_jsonb(row["summary"]) or None
    return ThesisGetResponse(
        thesis_id=row["id"],
        ticker=row["ticker"],
        focus_question=row["focus_question"],
        status=row["status"],
        research_stance=row["research_stance"],
        evidence_strength=(
            float(row["evidence_strength"]) if row["evidence_strength"] is not None
            else None
        ),
        dossier=summary,
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---------- GET /thesis/{id}/citations ----------


def _flatten_chunk_ids(rows: list[asyncpg.Record]) -> list[UUID]:
    seen: set[UUID] = set()
    out: list[UUID] = []
    for row in rows:
        for cid in row["chunk_ids"] or []:
            if cid not in seen:
                seen.add(cid)
                out.append(cid)
    return out


def _index_chunks(rows: list[asyncpg.Record]) -> dict[UUID, ChunkSnippet]:
    out: dict[UUID, ChunkSnippet] = {}
    for row in rows:
        out[row["chunk_id"]] = ChunkSnippet(
            chunk_id=row["chunk_id"],
            source_id=row["source_id"],
            text=row["text"],
            source_kind=row["source_kind"],
            source_provider=row["source_provider"],
            source_url=row["source_url"],
            source_title=row["source_title"],
        )
    return out


@router.get("/{thesis_id}/citations", response_model=CitationListResponse)
async def list_citations(
    thesis_id: UUID,
    conn: asyncpg.Connection = Depends(get_db_conn),
) -> CitationListResponse:
    citation_rows = list(await conn.fetch(_SELECT_CITATIONS, thesis_id))
    if not citation_rows:
        return CitationListResponse(citations=[])

    all_chunk_ids = _flatten_chunk_ids(citation_rows)
    chunk_rows = (
        list(await conn.fetch(_SELECT_CHUNKS_BY_IDS, all_chunk_ids))
        if all_chunk_ids else []
    )
    chunk_index = _index_chunks(chunk_rows)

    items: list[CitationListItem] = []
    for row in citation_rows:
        chunk_ids = list(row["chunk_ids"] or [])
        snippets = [chunk_index[cid] for cid in chunk_ids if cid in chunk_index]
        items.append(CitationListItem(
            id=row["id"],
            section=row["section"],
            claim=row["claim"],
            chunk_ids=chunk_ids,
            confidence=(
                float(row["confidence"]) if row["confidence"] is not None else None
            ),
            supporting_chunks=snippets,
            created_at=row["created_at"],
        ))
    return CitationListResponse(citations=items)


# ---------- GET /thesis/{id}/audit ----------


@router.get("/{thesis_id}/audit", response_model=AuditListResponse)
async def list_audit_events(
    thesis_id: UUID,
    limit: int = Query(default=200, ge=1, le=1000),
    conn: asyncpg.Connection = Depends(get_db_conn),
) -> AuditListResponse:
    rows = list(await conn.fetch(_SELECT_AUDIT, thesis_id, limit))
    events = [
        AuditEvent(
            id=row["id"],
            actor=row["actor"],
            action=row["action"],
            status=row["status"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cost_usd=(
                float(row["cost_usd"]) if row["cost_usd"] is not None else None
            ),
            latency_ms=row["latency_ms"],
            payload=_payload_to_dict(row["payload"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return AuditListResponse(events=events, total=len(events))


def _payload_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}
