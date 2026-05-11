from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from services.api import llm
from services.api.agents import synthesizer


class _FakeNewsItem(BaseModel):
    summary: str
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class _FakeNewsOutput(BaseModel):
    recent_events: list[_FakeNewsItem] = Field(default_factory=list)
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


def test_collect_chunk_ids_walks_nested_models() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    out = _FakeNewsOutput(
        recent_events=[
            _FakeNewsItem(summary="x", cited_chunk_ids=[a, b]),
        ],
        cited_chunk_ids=[c],
    )
    sink: set[UUID] = set()
    synthesizer._collect_chunk_ids({"news": out}, sink)
    assert sink == {a, b, c}


def test_synthetic_retrievals_carry_chunk_ids_only() -> None:
    a, b = uuid4(), uuid4()
    rs = synthesizer._synthetic_retrievals({a, b})
    assert {r.chunk_id for r in rs} == {a, b}
    assert all(r.text == "" for r in rs)
    assert all(r.source_id == synthesizer._SYNTHETIC_SOURCE_ID for r in rs)


def test_serialise_for_prompt_handles_pydantic_and_plain() -> None:
    out = _FakeNewsOutput(cited_chunk_ids=[uuid4()])
    rendered = synthesizer._serialise_for_prompt({"news": out, "raw": {"k": 1}})
    assert "recent_events" in rendered
    assert '"raw"' in rendered


async def test_synthesizer_run_filters_unknown_chunk_ids() -> None:
    """Synthesizer's runner must drop UUIDs the section agents never grounded,
    even though the synthesizer doesn't read raw chunks."""
    grounded = uuid4()
    bogus = uuid4()
    section = _FakeNewsOutput(cited_chunk_ids=[grounded])

    payload = {
        "executive_summary": "Acme is fine.",
        "executive_summary_cited_chunk_ids": [str(grounded), str(bogus)],
        "research_stance": "neutral",
        "evidence_strength": 0.5,
        "bull_case": [
            {"statement": "growth ok", "cited_chunk_ids": [str(grounded), str(bogus)]},
        ],
        "bear_case": [],
        "catalysts": [],
        "key_risks": [],
        "disconfirming_evidence": [],
        "macro_context": None,
        "macro_context_cited_chunk_ids": [],
        "valuation_summary": None,
        "valuation_summary_cited_chunk_ids": [],
        "quant_summary": None,
        "limitations": [],
        "analyst_disclaimer": "Default",
        "notes": None,
    }

    async def fake_llm(request: llm.LLMRequest, schema):
        out = schema.model_validate(payload)
        resp = llm.LLMResponse(
            text="...", parsed=payload, model="claude-sonnet-4-6",
            input_tokens=200, output_tokens=80, latency_ms=300,
            cost_usd=0.005, raw={"tool_input": payload},
        )
        return out, resp

    audit_calls: list[dict] = []

    async def fake_audit(**kwargs):
        audit_calls.append(kwargs)
        return uuid4()

    dossier = await synthesizer.run(
        "ACME",
        agent_outputs={"news": section},
        focus_question="how durable is growth?",
        llm_complete=fake_llm, audit_log=fake_audit,
    )

    # Bogus UUID dropped; grounded UUID survives.
    assert dossier.executive_summary_cited_chunk_ids == [grounded]
    assert dossier.bull_case[0].cited_chunk_ids == [grounded]
    assert audit_calls[0]["actor"] == "synthesizer"


async def test_synthesizer_drops_uncited_items() -> None:
    """A bull_case statement whose only chunk_id is bogus has no support and
    must be dropped, not retained with cited_chunk_ids=[]."""
    grounded = uuid4()
    bogus = uuid4()
    section = _FakeNewsOutput(cited_chunk_ids=[grounded])

    payload = {
        "executive_summary": "x",
        "executive_summary_cited_chunk_ids": [str(grounded)],
        "research_stance": "positive",
        "evidence_strength": 0.5,
        "bull_case": [
            {"statement": "supported", "cited_chunk_ids": [str(grounded)]},
            {"statement": "hallucinated", "cited_chunk_ids": [str(bogus)]},
        ],
        "bear_case": [],
        "catalysts": [],
        "key_risks": [],
        "disconfirming_evidence": [],
        "macro_context": None,
        "macro_context_cited_chunk_ids": [],
        "valuation_summary": None,
        "valuation_summary_cited_chunk_ids": [],
        "quant_summary": None,
        "limitations": [],
        "analyst_disclaimer": "x",
        "notes": None,
    }

    async def fake_llm(request, schema):
        return schema.model_validate(payload), llm.LLMResponse(
            text="x", parsed=payload, model="x",
            input_tokens=0, output_tokens=0, latency_ms=0, raw={},
        )

    async def fake_audit(**kwargs):
        return uuid4()

    dossier = await synthesizer.run(
        "X", agent_outputs={"news": section},
        llm_complete=fake_llm, audit_log=fake_audit,
    )
    assert [b.statement for b in dossier.bull_case] == ["supported"]
