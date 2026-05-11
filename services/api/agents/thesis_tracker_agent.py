"""Thesis tracker agent.

Inspired by Anthropic's Thesis Tracker pattern. Synthesises the structural
elements of a research thesis: pillars, disconfirming evidence, catalysts,
scorecard, and "what would change our mind". Sits between the section agents
(disclosure/news/macro/valuation) and the final synthesizer in 4c.

This agent benefits from seeing the *other* agents' outputs alongside the
retrieval set, so the orchestrator passes a JSON-rendered `agent_summaries`
template variable. The retrieval chunks are still passed for grounding new
claims that the section agents might not have surfaced.
"""
from __future__ import annotations

import json
from typing import Literal, Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from ..ingest._types import Retrieval
from ._base import run_agent

AGENT_NAME = "thesis_tracker_agent"
PROMPT_NAME = "thesis_tracker"

ResearchStance = Literal["positive", "neutral", "negative"]
DisconfirmSeverity = Literal["watch", "concern", "rebuts"]


class ThesisPillar(BaseModel):
    pillar: str
    """Short label, e.g. 'AI compute demand', 'pricing power', 'cost discipline'."""

    rationale: str
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class Catalyst(BaseModel):
    description: str
    expected_window: str | None = None
    """Free-text window when known, e.g. 'Q3 2026', 'next 12 months', 'AGM'."""

    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class DisconfirmingItem(BaseModel):
    description: str
    severity: DisconfirmSeverity = "watch"
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class ScorecardItem(BaseModel):
    pillar: str
    score: int = Field(ge=-2, le=2)
    """Integer in [-2, 2]. -2 = pillar materially broken, +2 = strongly supported."""

    rationale: str
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class ThesisTrackerOutput(BaseModel):
    thesis_statement: str
    """One paragraph (≤120 words) stating the analyst-facing thesis in prose."""

    research_stance: ResearchStance = "neutral"
    evidence_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    """0.0–1.0 estimate of how strongly the cited evidence supports the stance."""

    key_pillars: list[ThesisPillar] = Field(default_factory=list)
    disconfirming_evidence: list[DisconfirmingItem] = Field(default_factory=list)
    catalysts: list[Catalyst] = Field(default_factory=list)
    scorecard: list[ScorecardItem] = Field(default_factory=list)
    what_would_change_our_mind: list[str] = Field(default_factory=list)
    statement_cited_chunk_ids: list[UUID] = Field(default_factory=list)
    """Chunks supporting the thesis_statement paragraph specifically."""

    notes: str | None = None


async def run(
    ticker: str,
    *,
    retrievals: Sequence[Retrieval],
    agent_summaries: dict[str, object] | None = None,
    focus_question: str | None = None,
    thesis_id: UUID | None = None,
    job_id: UUID | None = None,
    model: str | None = None,
    llm_complete=None,
    audit_log=None,
) -> ThesisTrackerOutput:
    rendered = json.dumps(agent_summaries or {}, indent=2, default=str)
    return await run_agent(
        agent_name=AGENT_NAME,
        prompt_name=PROMPT_NAME,
        output_schema=ThesisTrackerOutput,
        retrievals=retrievals,
        template_vars={
            "ticker": ticker,
            "focus_question": focus_question or "(none)",
            "agent_summaries": rendered,
        },
        model=model,
        thesis_id=thesis_id,
        job_id=job_id,
        llm_complete=llm_complete,
        audit_log=audit_log,
    )
