"""Valuation agent (light).

Phase 4 deliberately keeps this simple: no DCF, no fabricated multiples. The
agent reads disclosure + peer-context chunks and surfaces what's stated, peer
context where supportable, and any number it cannot ground in a chunk goes
into `unsourced_numbers` so the synthesizer can mark it `[UNSOURCED]`.
"""
from __future__ import annotations

from typing import Literal, Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from ..ingest._types import Retrieval
from ._base import run_agent

AGENT_NAME = "valuation_agent"
PROMPT_NAME = "valuation"

Severity = Literal["info", "watch", "warn"]


class PeerContext(BaseModel):
    peer: str
    metric: str
    """Metric label, e.g. 'EV/EBITDA', 'P/E NTM', 'dividend yield'."""

    value: str | None = None
    """Free-text value as stated, e.g. '12.5x' or '3.2%'. Null when the chunk
    doesn't state the metric for this peer."""

    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class ValuationFlag(BaseModel):
    description: str
    severity: Severity = "info"
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class ValuationAgentOutput(BaseModel):
    valuation_summary: str
    """One paragraph (≤120 words). State only what the chunks support; flag absences explicitly."""

    peer_context: list[PeerContext] = Field(default_factory=list)
    valuation_flags: list[ValuationFlag] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    unsourced_numbers: list[str] = Field(default_factory=list)
    """Numbers that appear in the summary but couldn't be tied to a specific chunk —
    the synthesizer surfaces these as `[UNSOURCED]`."""

    summary_cited_chunk_ids: list[UUID] = Field(default_factory=list)
    notes: str | None = None


async def run(
    ticker: str,
    *,
    retrievals: Sequence[Retrieval],
    thesis_id: UUID | None = None,
    job_id: UUID | None = None,
    model: str | None = None,
    llm_complete=None,
    audit_log=None,
) -> ValuationAgentOutput:
    return await run_agent(
        agent_name=AGENT_NAME,
        prompt_name=PROMPT_NAME,
        output_schema=ValuationAgentOutput,
        retrievals=retrievals,
        template_vars={"ticker": ticker},
        model=model,
        thesis_id=thesis_id,
        job_id=job_id,
        llm_complete=llm_complete,
        audit_log=audit_log,
    )
