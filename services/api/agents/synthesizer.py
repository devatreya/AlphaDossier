"""Synthesizer — composes all agent outputs into the final dossier.

Unlike a section agent, the synthesizer doesn't read raw chunks. It reads the
*structured outputs* of the section agents (already grounded and filtered) and
weaves them into the analyst-facing dossier.

Citation discipline is preserved: we collect every chunk_id any section agent
cited, build synthetic `Retrieval` objects from that set, and pass them into
`run_agent` as the "existing" set used by the citation filter. Anything the
synthesizer references that none of the section agents grounded will be
dropped, exactly like a hallucinated UUID.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ..ingest._types import Retrieval
from ._base import _is_citation_field, run_agent
from .thesis_tracker_agent import ResearchStance

AGENT_NAME = "synthesizer"
PROMPT_NAME = "synthesis"

_SYNTHETIC_SOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")
_DEFAULT_DISCLAIMER = (
    "This dossier is research-prototype output and is not investment advice. "
    "Verify all claims against primary sources before acting on it."
)


class CitedStatement(BaseModel):
    statement: str
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class FinalDossier(BaseModel):
    executive_summary: str
    """One paragraph (≤150 words) that an analyst could read first."""

    executive_summary_cited_chunk_ids: list[UUID] = Field(default_factory=list)

    research_stance: ResearchStance = "neutral"
    evidence_strength: float = Field(default=0.0, ge=0.0, le=1.0)

    bull_case: list[CitedStatement] = Field(default_factory=list)
    bear_case: list[CitedStatement] = Field(default_factory=list)
    catalysts: list[CitedStatement] = Field(default_factory=list)
    key_risks: list[CitedStatement] = Field(default_factory=list)
    disconfirming_evidence: list[CitedStatement] = Field(default_factory=list)

    macro_context: str | None = None
    macro_context_cited_chunk_ids: list[UUID] = Field(default_factory=list)

    valuation_summary: str | None = None
    valuation_summary_cited_chunk_ids: list[UUID] = Field(default_factory=list)

    quant_summary: str | None = None
    """Free-text rendering of the price/quant_validation outputs.

    No chunk citations here — the price/quant agents don't read chunks; their
    outputs are already cited via their `metadata` and `notes`."""

    limitations: list[str] = Field(default_factory=list)
    analyst_disclaimer: str = _DEFAULT_DISCLAIMER
    notes: str | None = None


def _collect_chunk_ids(value: Any, sink: set[UUID]) -> None:
    """Walk Pydantic / list / dict trees, collecting every UUID in any
    citation-style field. Mirrors `_walk_and_filter` so the existing-set we
    feed to `run_agent` matches exactly the IDs the section agents grounded.
    """
    if isinstance(value, BaseModel):
        for field_name in type(value).model_fields:
            current = getattr(value, field_name)
            if _is_citation_field(field_name) and isinstance(current, list):
                for cid in current:
                    if isinstance(cid, UUID):
                        sink.add(cid)
                continue
            _collect_chunk_ids(current, sink)
        return
    if isinstance(value, list):
        for item in value:
            _collect_chunk_ids(item, sink)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_chunk_ids(item, sink)
        return


def _synthetic_retrievals(chunk_ids: set[UUID]) -> list[Retrieval]:
    """Fake Retrieval objects that exist purely so the runner's UUID filter
    knows which chunk_ids are 'real'. Text is empty — the synthesis prompt
    doesn't render `{context}`, so this content never reaches the model."""
    return [
        Retrieval(
            chunk_id=cid,
            source_id=_SYNTHETIC_SOURCE_ID,
            text="",
            chunk_index=0,
            similarity=0.0,
            metadata={},
        )
        for cid in chunk_ids
    ]


def _serialise_for_prompt(agent_outputs: dict[str, Any]) -> str:
    """Render agent outputs as readable JSON, excluding bulky fields the
    synthesizer doesn't need to re-read (raw chunk text, embeddings)."""

    def coerce(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        return value

    serialised = {name: coerce(out) for name, out in agent_outputs.items()}
    return json.dumps(serialised, indent=2, default=str)


async def run(
    ticker: str,
    *,
    agent_outputs: dict[str, Any],
    focus_question: str | None = None,
    thesis_id: UUID | None = None,
    job_id: UUID | None = None,
    model: str | None = None,
    llm_complete=None,
    audit_log=None,
) -> FinalDossier:
    """Run the synthesizer over a bag of section-agent outputs.

    `agent_outputs` is a dict like
        {"news": NewsAgentOutput, "disclosure": DisclosureAgentOutput,
         "thesis_tracker": ThesisTrackerOutput, "price": PriceAgentOutput, ...}.
    Missing agents (unavailable due to missing keys, errors, or region) simply
    won't appear; the synthesizer prompt says to handle gaps gracefully.
    """
    chunk_ids: set[UUID] = set()
    _collect_chunk_ids(agent_outputs, chunk_ids)

    return await run_agent(
        agent_name=AGENT_NAME,
        prompt_name=PROMPT_NAME,
        output_schema=FinalDossier,
        retrievals=_synthetic_retrievals(chunk_ids),
        template_vars={
            "ticker": ticker,
            "focus_question": focus_question or "(none)",
            "agent_outputs": _serialise_for_prompt(agent_outputs),
        },
        model=model,
        max_tokens=8192,
        thesis_id=thesis_id,
        job_id=job_id,
        llm_complete=llm_complete,
        audit_log=audit_log,
    )
