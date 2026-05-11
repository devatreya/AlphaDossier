"""HTTP API response/request schemas.

The FinalDossier produced by the synthesizer is stored in the `theses.summary`
column as jsonb. We return it through the API as an opaque dict; the frontend
type definitions in apps/web/lib/types.ts mirror its shape.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ThesisCreateRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=15)
    focus_question: str | None = Field(default=None, max_length=500)


class ThesisCreateResponse(BaseModel):
    thesis_id: UUID
    status: str  # "pending"


class ThesisGetResponse(BaseModel):
    thesis_id: UUID
    ticker: str
    focus_question: str | None = None
    status: str
    research_stance: str | None = None
    evidence_strength: float | None = None
    dossier: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ChunkSnippet(BaseModel):
    chunk_id: UUID
    source_id: UUID
    text: str
    source_kind: str | None = None
    source_provider: str | None = None
    source_url: str | None = None
    source_title: str | None = None


class CitationListItem(BaseModel):
    id: UUID
    section: str
    claim: str
    chunk_ids: list[UUID]
    confidence: float | None = None
    supporting_chunks: list[ChunkSnippet] = Field(default_factory=list)
    created_at: datetime


class CitationListResponse(BaseModel):
    citations: list[CitationListItem]


class AuditEvent(BaseModel):
    id: UUID
    actor: str
    action: str
    status: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AuditListResponse(BaseModel):
    events: list[AuditEvent]
    total: int
