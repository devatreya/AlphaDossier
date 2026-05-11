"""Phase 3 types shared by chunker, embedder, retriever, citations."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A unit of text ready to be embedded. Position-aware so we can rebuild
    citations and show where a quote came from inside a source."""

    text: str
    chunk_index: int
    token_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class Retrieval(BaseModel):
    """A retrieval hit: chunk text + similarity score + source metadata.

    Phase 4 agents read these; the synthesizer renders citations from them.
    """

    chunk_id: UUID
    source_id: UUID
    text: str
    similarity: float
    chunk_index: int
    source_kind: str | None = None
    source_provider: str | None = None
    source_url: str | None = None
    source_title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoredSource(BaseModel):
    """A `sources` row read back from the DB. `metadata` is always a dict."""

    id: UUID
    thesis_id: UUID | None = None
    kind: str
    provider: str
    url: str | None = None
    title: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    raw_path: str | None = None
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoredChunk(BaseModel):
    """A `chunks` row read back from the DB.

    Embeddings are intentionally omitted from the default read API — they are
    large and rarely needed by callers, who typically want chunk text + source
    context. Use the retriever for similarity search.
    """

    id: UUID
    source_id: UUID
    chunk_index: int
    text: str
    token_count: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CitationValidation(BaseModel):
    """Heuristic check of whether a claim is supported by its cited chunks."""

    ok: bool
    overlap_score: float
    """Fraction of the claim's content terms that appear in any cited chunk."""

    matched_terms: list[str] = Field(default_factory=list)
    missing_terms: list[str] = Field(default_factory=list)
    reason: str | None = None
