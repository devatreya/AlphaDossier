"""Regression tests for Phase 4b review findings.

Covers:
  1. Summary-specific citation fields (`headline_*`, `summary_*`, `statement_*`,
     `sector_*`, `market_structure_*`, `business_summary_*`, `macro_regime_*`)
     must go through the same UUID filter as plain `cited_chunk_ids`.
  2. ThesisTrackerOutput.evidence_strength is bounded [0, 1].
  3. ScorecardItem.score is bounded [-2, 2].
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import BaseModel, Field, ValidationError

from services.api import llm
from services.api.agents._base import _is_citation_field, run_agent
from services.api.agents.thesis_tracker_agent import (
    ScorecardItem,
    ThesisPillar,
    ThesisTrackerOutput,
)
from services.api.ingest._types import Retrieval


# ---------- Citation matcher ----------


def test_is_citation_field_matches_summary_variants() -> None:
    assert _is_citation_field("cited_chunk_ids")
    assert _is_citation_field("headline_cited_chunk_ids")
    assert _is_citation_field("summary_cited_chunk_ids")
    assert _is_citation_field("statement_cited_chunk_ids")
    assert _is_citation_field("sector_cited_chunk_ids")
    assert _is_citation_field("market_structure_cited_chunk_ids")
    assert _is_citation_field("business_summary_cited_chunk_ids")
    assert _is_citation_field("macro_regime_cited_chunk_ids")
    # Legacy alias from the project plan's example schemas.
    assert _is_citation_field("citation_ids")


def test_is_citation_field_rejects_unrelated_names() -> None:
    assert not _is_citation_field("summary")
    assert not _is_citation_field("name")
    assert not _is_citation_field("score")
    assert not _is_citation_field("data_points")


# ---------- Runner filters new citation field shapes ----------


class _SchemaWithSummaryCitations(BaseModel):
    """A schema modelled on earnings_reviewer/valuation/thesis_tracker — the
    citation field is a per-section variant, not the canonical name."""

    headline_read: str
    headline_cited_chunk_ids: list = Field(default_factory=list)


def _retrieval() -> Retrieval:
    return Retrieval(
        chunk_id=uuid4(), source_id=uuid4(),
        text="x", chunk_index=0, similarity=0.8,
        source_kind="news", source_provider="news_api",
        source_url=None, source_title=None, metadata={},
    )


async def test_runner_filters_summary_specific_citation_field() -> None:
    rs = [_retrieval()]
    valid_id = rs[0].chunk_id
    bogus_id = uuid4()

    async def fake_llm(request: llm.LLMRequest, schema):
        out = schema.model_validate({
            "headline_read": "Beat-and-raise quarter",
            "headline_cited_chunk_ids": [valid_id, bogus_id],
        })
        resp = llm.LLMResponse(
            text="...", parsed=None, model="claude-sonnet-4-6",
            input_tokens=10, output_tokens=5, latency_ms=100, cost_usd=0.001,
            raw={},
        )
        return out, resp

    async def fake_audit(**kwargs):
        return uuid4()

    # The schema needs a prompt; reuse 'news' since we're only testing the
    # runner's filtering logic, not prompt rendering.
    out = await run_agent(
        agent_name="test_agent",
        prompt_name="news",
        output_schema=_SchemaWithSummaryCitations,
        retrievals=rs,
        template_vars={"ticker": "X"},
        llm_complete=fake_llm,
        audit_log=fake_audit,
    )

    # The bogus UUID must have been filtered, not preserved.
    assert out.headline_cited_chunk_ids == [valid_id]


# ---------- Bounded scoring fields ----------


def test_evidence_strength_above_one_rejected() -> None:
    with pytest.raises(ValidationError):
        ThesisTrackerOutput(thesis_statement="x", evidence_strength=7.5)


def test_evidence_strength_below_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        ThesisTrackerOutput(thesis_statement="x", evidence_strength=-0.1)


def test_evidence_strength_inside_bounds_accepted() -> None:
    out = ThesisTrackerOutput(thesis_statement="x", evidence_strength=0.5)
    assert out.evidence_strength == 0.5


def test_evidence_strength_at_bounds_accepted() -> None:
    ThesisTrackerOutput(thesis_statement="x", evidence_strength=0.0)
    ThesisTrackerOutput(thesis_statement="x", evidence_strength=1.0)


def test_scorecard_score_above_two_rejected() -> None:
    with pytest.raises(ValidationError):
        ScorecardItem(pillar="p", score=99, rationale="r")


def test_scorecard_score_below_minus_two_rejected() -> None:
    with pytest.raises(ValidationError):
        ScorecardItem(pillar="p", score=-3, rationale="r")


def test_scorecard_score_at_bounds_accepted() -> None:
    for s in (-2, -1, 0, 1, 2):
        ScorecardItem(pillar="p", score=s, rationale="r")


def test_thesis_tracker_full_output_with_bounded_scorecard() -> None:
    """Round-trip a realistic output to confirm pillar + score validation
    composes cleanly."""
    cid = uuid4()
    out = ThesisTrackerOutput(
        thesis_statement="...",
        research_stance="positive",
        evidence_strength=0.6,
        key_pillars=[ThesisPillar(pillar="P1", rationale="r", cited_chunk_ids=[cid])],
        scorecard=[
            ScorecardItem(pillar="P1", score=2, rationale="r", cited_chunk_ids=[cid]),
            ScorecardItem(pillar="P2", score=-2, rationale="r", cited_chunk_ids=[cid]),
        ],
    )
    assert [s.score for s in out.scorecard] == [2, -2]
