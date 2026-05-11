"""Earnings reviewer agent.

Inspired by Anthropic's Earnings Reviewer pattern — reads results-related
chunks (transcripts where available, results RNS, results presentation PDFs,
8-K earnings releases, results articles) and produces a structured review.
"""
from __future__ import annotations

from typing import Literal, Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from ..ingest._types import Retrieval
from ._base import run_agent

AGENT_NAME = "earnings_reviewer_agent"
PROMPT_NAME = "earnings_reviewer"

Direction = Literal["up", "down", "flat", "unclear"]
ManagementTone = Literal["positive", "neutral", "negative", "mixed", "unclear"]
ThesisImpact = Literal["strengthens", "weakens", "neutral", "unclear"]


class MetricChange(BaseModel):
    metric: str
    """Short metric label, e.g. 'revenue', 'gross margin', 'FY26 guidance midpoint'."""

    direction: Direction
    magnitude: str | None = None
    """Free-text magnitude when stated, e.g. '+12% YoY' or '$2.1B'."""

    period: str | None = None
    """Reporting period the metric refers to, e.g. 'Q3 2026'."""

    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class EarningsReviewerOutput(BaseModel):
    headline_read: str
    """One-paragraph synthesis (≤120 words) of how this print should land for the thesis."""

    key_metric_changes: list[MetricChange] = Field(default_factory=list)
    guidance_changes: list[MetricChange] = Field(default_factory=list)
    management_tone: ManagementTone = "unclear"
    thesis_impact: ThesisImpact = "unclear"
    missing_data: list[str] = Field(default_factory=list)
    """Things you would have liked to read but the chunks did not cover."""

    headline_cited_chunk_ids: list[UUID] = Field(default_factory=list)
    """Chunks supporting the headline_read paragraph specifically."""

    notes: str | None = None


async def run(
    ticker: str,
    *,
    retrievals: Sequence[Retrieval],
    focus_question: str | None = None,
    thesis_id: UUID | None = None,
    job_id: UUID | None = None,
    model: str | None = None,
    llm_complete=None,
    audit_log=None,
) -> EarningsReviewerOutput:
    return await run_agent(
        agent_name=AGENT_NAME,
        prompt_name=PROMPT_NAME,
        output_schema=EarningsReviewerOutput,
        retrievals=retrievals,
        template_vars={
            "ticker": ticker,
            "focus_question": focus_question or "(none)",
        },
        model=model,
        thesis_id=thesis_id,
        job_id=job_id,
        llm_complete=llm_complete,
        audit_log=audit_log,
    )
