"""UK RNS agent.

Reads RNS-style announcements (or the Phase 2 News-API proxy tagged
`kind="rns_proxy"`) and extracts the items a UK-focused analyst cares about:
recent events, price-sensitive items, guidance/outlook changes, and risks.
"""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from ..ingest._types import Retrieval
from ._base import run_agent

AGENT_NAME = "uk_rns_agent"
PROMPT_NAME = "uk_rns"


class RnsItem(BaseModel):
    summary: str
    event_date: str | None = None
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class UkRnsAgentOutput(BaseModel):
    recent_rns_events: list[RnsItem] = Field(default_factory=list)
    price_sensitive_items: list[RnsItem] = Field(default_factory=list)
    guidance_or_outlook_changes: list[RnsItem] = Field(default_factory=list)
    risk_items: list[RnsItem] = Field(default_factory=list)
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
) -> UkRnsAgentOutput:
    return await run_agent(
        agent_name=AGENT_NAME,
        prompt_name=PROMPT_NAME,
        output_schema=UkRnsAgentOutput,
        retrievals=retrievals,
        template_vars={"ticker": ticker},
        model=model,
        thesis_id=thesis_id,
        job_id=job_id,
        llm_complete=llm_complete,
        audit_log=audit_log,
    )
