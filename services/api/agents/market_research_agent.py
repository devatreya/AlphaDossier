"""Market research agent.

Inspired by Anthropic's Market Researcher pattern. Builds a sector + competitive
view from disclosures, news, and any peer commentary in the retrieval set.
"""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from ..ingest._types import Retrieval
from ._base import run_agent

AGENT_NAME = "market_research_agent"
PROMPT_NAME = "market_research"


class CitedStatement(BaseModel):
    statement: str
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class Peer(BaseModel):
    name: str
    """Ticker or company name as it appears in the chunk."""

    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class MarketResearchOutput(BaseModel):
    sector: str
    """Short sector label, e.g. 'integrated oil & gas', 'large-cap pharma'."""

    sector_cited_chunk_ids: list[UUID] = Field(default_factory=list)

    market_structure: str
    """One paragraph (≤120 words) describing concentration, distribution, and economics."""

    market_structure_cited_chunk_ids: list[UUID] = Field(default_factory=list)
    """Chunks supporting the market_structure paragraph specifically."""

    key_drivers: list[CitedStatement] = Field(default_factory=list)
    """Demand or supply drivers that move the sector — each cited."""

    peer_set: list[Peer] = Field(default_factory=list)
    """Peers in approximate order of comparability. Each name must cite the
    chunk that supports its inclusion — uncited peers are dropped."""

    competitive_positioning: list[CitedStatement] = Field(default_factory=list)
    """Where this issuer sits vs peers (cost, scale, geography, technology)."""

    theme_readthrough: list[CitedStatement] = Field(default_factory=list)
    """Cross-cutting themes (regulation, tech shift, macro) and their implications."""

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
) -> MarketResearchOutput:
    return await run_agent(
        agent_name=AGENT_NAME,
        prompt_name=PROMPT_NAME,
        output_schema=MarketResearchOutput,
        retrievals=retrievals,
        template_vars={"ticker": ticker},
        model=model,
        thesis_id=thesis_id,
        job_id=job_id,
        llm_complete=llm_complete,
        audit_log=audit_log,
    )
