"""Disclosure agent.

Analyses regulated filings — US 10-K/10-Q/8-K (and 20-F/6-K for foreign issuers)
or UK annual/half-year reports and trading updates. The orchestrator selects
the right source kinds for the issuer's region and feeds the retrieved chunks
in.
"""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from ..ingest._types import Retrieval
from ._base import run_agent

AGENT_NAME = "disclosure_agent"
PROMPT_NAME = "disclosure"


class DisclosureItem(BaseModel):
    summary: str
    quoted_passage: str | None = None
    """Optional short verbatim quote (≤30 words) from the cited chunk."""

    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class DisclosureAgentOutput(BaseModel):
    business_summary: str
    """One-paragraph factual description of what the issuer does, grounded in the filings."""

    business_summary_cited_chunk_ids: list[UUID] = Field(default_factory=list)
    """Chunks supporting the business_summary paragraph specifically."""

    key_disclosure_claims: list[DisclosureItem] = Field(default_factory=list)
    risk_factors: list[DisclosureItem] = Field(default_factory=list)
    guidance_changes: list[DisclosureItem] = Field(default_factory=list)
    capital_allocation: list[DisclosureItem] = Field(default_factory=list)
    balance_sheet_notes: list[DisclosureItem] = Field(default_factory=list)
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
) -> DisclosureAgentOutput:
    return await run_agent(
        agent_name=AGENT_NAME,
        prompt_name=PROMPT_NAME,
        output_schema=DisclosureAgentOutput,
        retrievals=retrievals,
        template_vars={"ticker": ticker},
        model=model,
        thesis_id=thesis_id,
        job_id=job_id,
        llm_complete=llm_complete,
        audit_log=audit_log,
    )
