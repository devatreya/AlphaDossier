"""UK macro agent.

Same shape as macro_agent but consumes ONS / Bank of England series, plus
optionally cross-market FRED indicators for comparison.
"""
from __future__ import annotations

import json
from typing import Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from ..ingest._types import Retrieval
from ._base import run_agent
from .macro_agent import MacroFactor

AGENT_NAME = "uk_macro_agent"
PROMPT_NAME = "uk_macro"


class UkMacroOutput(BaseModel):
    uk_macro_context: str
    """One paragraph (≤120 words) on the current UK regime: growth, CPI, Bank Rate, sterling."""

    bank_rate_context: str
    """Short statement on the Bank Rate path implied by the chunks/data_points."""

    inflation_context: str
    """Short statement on UK inflation trajectory."""

    sterling_or_rates_sensitivity: list[MacroFactor] = Field(default_factory=list)
    relevant_data_points: dict[str, str] = Field(default_factory=dict)
    cited_chunk_ids: list[UUID] = Field(default_factory=list)
    """Chunks supporting the three context paragraphs collectively."""

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
) -> UkMacroOutput:
    rendered = json.dumps(data_points or {}, indent=2, default=str)
    return await run_agent(
        agent_name=AGENT_NAME,
        prompt_name=PROMPT_NAME,
        output_schema=UkMacroOutput,
        retrievals=retrievals,
        template_vars={"ticker": ticker, "data_points": rendered},
        model=model,
        thesis_id=thesis_id,
        job_id=job_id,
        llm_complete=llm_complete,
        audit_log=audit_log,
    )
