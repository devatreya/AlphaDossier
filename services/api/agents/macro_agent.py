"""Macro agent (US-focused).

Reads a snapshot of FRED series the orchestrator pre-fetched plus any
macro-flavoured news in the retrieval set, then interprets the macro regime
for `ticker`. Numeric `data_points` are factual (from FRED) so they don't need
chunk citations; qualitative `MacroFactor` items must cite chunks.
"""
from __future__ import annotations

import json
from typing import Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from ..ingest._types import Retrieval
from ._base import run_agent

AGENT_NAME = "macro_agent"
PROMPT_NAME = "macro"


class MacroFactor(BaseModel):
    name: str
    """Short label, e.g. 'real rates', 'USD trade-weighted', 'credit spreads'."""

    description: str
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class MacroAgentOutput(BaseModel):
    macro_regime: str
    """One paragraph (≤120 words) on the current US macro regime."""

    macro_regime_cited_chunk_ids: list[UUID] = Field(default_factory=list)
    """Chunks supporting the macro_regime paragraph. Numeric data points are
    factual from FRED and don't need chunk citations."""

    relevant_macro_factors: list[MacroFactor] = Field(default_factory=list)
    ticker_sensitivity: list[MacroFactor] = Field(default_factory=list)
    macro_tailwinds: list[MacroFactor] = Field(default_factory=list)
    macro_risks: list[MacroFactor] = Field(default_factory=list)
    data_points_used: dict[str, str] = Field(default_factory=dict)
    """Subset of provided data_points the agent treated as load-bearing, with units."""

    notes: str | None = None


async def run(
    ticker: str,
    *,
    retrievals: Sequence[Retrieval],
    data_points: dict[str, object] | None = None,
    thesis_id: UUID | None = None,
    job_id: UUID | None = None,
    model: str | None = None,
    llm_complete=None,
    audit_log=None,
) -> MacroAgentOutput:
    rendered = json.dumps(data_points or {}, indent=2, default=str)
    return await run_agent(
        agent_name=AGENT_NAME,
        prompt_name=PROMPT_NAME,
        output_schema=MacroAgentOutput,
        retrievals=retrievals,
        template_vars={"ticker": ticker, "data_points": rendered},
        model=model,
        thesis_id=thesis_id,
        job_id=job_id,
        llm_complete=llm_complete,
        audit_log=audit_log,
    )
