"""News research agent.

Reads news chunks (typically retrieved over the last ~90 days) and produces
four typed lists: recent events, high-severity items, regulatory/legal items,
and sector read-through. Output schema mirrors the contract in the project plan.
"""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from ..ingest._types import Retrieval
from ._base import run_agent

AGENT_NAME = "news_agent"
PROMPT_NAME = "news"


class NewsItem(BaseModel):
    summary: str
    """One-sentence factual statement."""

    cited_chunk_ids: list[UUID] = Field(default_factory=list)
    """UUIDs from the retrieved context that support this item."""

    event_date: str | None = None
    """ISO date if the chunk states one, else null. NOT the publication date."""


class NewsAgentOutput(BaseModel):
    recent_events: list[NewsItem] = Field(default_factory=list)
    high_severity_news: list[NewsItem] = Field(default_factory=list)
    regulatory_or_legal_items: list[NewsItem] = Field(default_factory=list)
    sector_readthrough: list[NewsItem] = Field(default_factory=list)
    notes: str | None = None
    """Free-form note from the agent — usually 'no news found' or coverage gaps."""


async def run(
    ticker: str,
    *,
    retrievals: Sequence[Retrieval],
    thesis_id: UUID | None = None,
    job_id: UUID | None = None,
    model: str | None = None,
    llm_complete=None,
    audit_log=None,
) -> NewsAgentOutput:
    return await run_agent(
        agent_name=AGENT_NAME,
        prompt_name=PROMPT_NAME,
        output_schema=NewsAgentOutput,
        retrievals=retrievals,
        template_vars={"ticker": ticker},
        model=model,
        thesis_id=thesis_id,
        job_id=job_id,
        llm_complete=llm_complete,
        audit_log=audit_log,
    )
