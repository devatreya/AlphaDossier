"""Smoke tests for the eight Phase 4b LLM agents.

Each agent is a thin wrapper around `run_agent`. The runner itself is covered
exhaustively by test_base_agent. Here we verify per agent:

  1. The agent's output schema is a real Pydantic model.
  2. The corresponding prompts/<name>.md exists and renders with the variables
     the agent passes.
  3. A stubbed LLM that returns a minimal valid output for the schema flows
     through the runner unchanged, audit fires, and citation filtering works.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from services.api import config, llm
from services.api.agents import (
    _prompts,
    disclosure_agent,
    earnings_reviewer_agent,
    macro_agent,
    market_research_agent,
    thesis_tracker_agent,
    uk_macro_agent,
    uk_rns_agent,
    valuation_agent,
)
from services.api.ingest._types import Retrieval


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    config.get_settings.cache_clear()


def _retrieval(text: str = "x") -> Retrieval:
    return Retrieval(
        chunk_id=uuid4(), source_id=uuid4(),
        text=text, chunk_index=0, similarity=0.8,
        source_kind="news", source_provider="news_api",
        source_url=None, source_title=None, metadata={},
    )


def _stub_llm(payload: dict[str, Any]):
    async def fn(request: llm.LLMRequest, schema):
        out = schema.model_validate(payload)
        resp = llm.LLMResponse(
            text="ok", parsed=payload,
            model="claude-sonnet-4-6",
            input_tokens=10, output_tokens=5,
            latency_ms=100, cost_usd=0.001,
            raw={"tool_input": payload},
        )
        return out, resp
    return fn


def _capture_audit() -> tuple[list[dict], Any]:
    captured: list[dict] = []

    async def fn(**kwargs: Any) -> UUID:
        captured.append(kwargs)
        return uuid4()

    return captured, fn


# ----------------------------- prompt presence -----------------------------


@pytest.mark.parametrize(
    "name",
    [
        "disclosure", "uk_rns", "earnings_reviewer", "market_research",
        "macro", "uk_macro", "valuation", "thesis_tracker",
    ],
)
def test_prompt_files_exist(name: str) -> None:
    text = _prompts.load_prompt(name)
    assert "{ticker}" in text
    assert "{context}" in text


def test_macro_prompts_reference_data_points() -> None:
    assert "{data_points}" in _prompts.load_prompt("macro")
    assert "{data_points}" in _prompts.load_prompt("uk_macro")


def test_thesis_tracker_prompt_references_agent_summaries() -> None:
    assert "{agent_summaries}" in _prompts.load_prompt("thesis_tracker")


def test_earnings_prompt_references_focus_question() -> None:
    assert "{focus_question}" in _prompts.load_prompt("earnings_reviewer")


# ----------------------------- per-agent runs -----------------------------


async def test_disclosure_agent_runs() -> None:
    rs = [_retrieval()]
    cid = str(rs[0].chunk_id)
    payload = {
        "business_summary": "Acme makes widgets.",
        "business_summary_cited_chunk_ids": [cid],
        "key_disclosure_claims": [
            {"summary": "Top customer is 15% of revenue", "cited_chunk_ids": [cid]},
        ],
        "risk_factors": [],
        "guidance_changes": [],
        "capital_allocation": [],
        "balance_sheet_notes": [],
        "notes": None,
    }
    captured, audit_fn = _capture_audit()
    out = await disclosure_agent.run(
        "ACME", retrievals=rs, llm_complete=_stub_llm(payload), audit_log=audit_fn,
    )
    assert out.business_summary == "Acme makes widgets."
    assert out.business_summary_cited_chunk_ids == [rs[0].chunk_id]
    assert len(out.key_disclosure_claims) == 1
    assert captured[0]["actor"] == "disclosure_agent"


async def test_uk_rns_agent_runs() -> None:
    rs = [_retrieval()]
    cid = str(rs[0].chunk_id)
    payload = {
        "recent_rns_events": [
            {"summary": "FY trading update", "event_date": "2026-04-30", "cited_chunk_ids": [cid]},
        ],
        "price_sensitive_items": [],
        "guidance_or_outlook_changes": [],
        "risk_items": [],
        "notes": None,
    }
    captured, audit_fn = _capture_audit()
    out = await uk_rns_agent.run(
        "SHEL.L", retrievals=rs, llm_complete=_stub_llm(payload), audit_log=audit_fn,
    )
    assert out.recent_rns_events[0].event_date == "2026-04-30"
    assert captured[0]["actor"] == "uk_rns_agent"


async def test_earnings_reviewer_runs() -> None:
    rs = [_retrieval()]
    cid = str(rs[0].chunk_id)
    payload = {
        "headline_read": "Beat on revenue, soft guide.",
        "key_metric_changes": [
            {
                "metric": "revenue", "direction": "up", "magnitude": "+12% YoY",
                "period": "Q1 2026", "cited_chunk_ids": [cid],
            },
        ],
        "guidance_changes": [
            {
                "metric": "FY revenue", "direction": "down", "magnitude": "-3%",
                "period": "FY 2026", "cited_chunk_ids": [cid],
            },
        ],
        "management_tone": "mixed",
        "thesis_impact": "neutral",
        "missing_data": ["no segment FCF disclosed"],
        "headline_cited_chunk_ids": [cid],
        "notes": None,
    }
    captured, audit_fn = _capture_audit()
    out = await earnings_reviewer_agent.run(
        "ACME", retrievals=rs, focus_question="how is the consumer segment?",
        llm_complete=_stub_llm(payload), audit_log=audit_fn,
    )
    assert out.management_tone == "mixed"
    assert out.thesis_impact == "neutral"
    assert captured[0]["payload"]["template_vars"]["focus_question"] == (
        "how is the consumer segment?"
    )


async def test_market_research_runs() -> None:
    rs = [_retrieval()]
    cid = str(rs[0].chunk_id)
    payload = {
        "sector": "integrated oil & gas",
        "sector_cited_chunk_ids": [cid],
        "market_structure": "Concentrated supermajors plus NOCs.",
        "market_structure_cited_chunk_ids": [cid],
        "key_drivers": [
            {"statement": "Brent prices drive upstream cash", "cited_chunk_ids": [cid]},
        ],
        "peer_set": [
            {"name": "XOM", "cited_chunk_ids": [cid]},
            {"name": "CVX", "cited_chunk_ids": [cid]},
            {"name": "BP.L", "cited_chunk_ids": [cid]},
        ],
        "competitive_positioning": [],
        "theme_readthrough": [],
        "notes": None,
    }
    captured, audit_fn = _capture_audit()
    out = await market_research_agent.run(
        "SHEL.L", retrievals=rs, llm_complete=_stub_llm(payload), audit_log=audit_fn,
    )
    assert out.sector == "integrated oil & gas"
    assert [p.name for p in out.peer_set] == ["XOM", "CVX", "BP.L"]
    assert out.sector_cited_chunk_ids == [rs[0].chunk_id]
    assert out.market_structure_cited_chunk_ids == [rs[0].chunk_id]
    assert captured[0]["actor"] == "market_research_agent"


async def test_macro_agent_runs_with_data_points() -> None:
    rs = [_retrieval()]
    cid = str(rs[0].chunk_id)
    payload = {
        "macro_regime": "Late-cycle US with sticky services inflation.",
        "macro_regime_cited_chunk_ids": [cid],
        "relevant_macro_factors": [
            {"name": "real rates", "description": "10y real ~2%", "cited_chunk_ids": [cid]},
        ],
        "ticker_sensitivity": [],
        "macro_tailwinds": [],
        "macro_risks": [],
        "data_points_used": {"DGS10": "10Y nominal yield, %"},
        "notes": None,
    }
    captured, audit_fn = _capture_audit()
    out = await macro_agent.run(
        "NVDA",
        retrievals=rs,
        data_points={"DGS10": 4.20, "CPIAUCSL_yoy": 3.1},
        llm_complete=_stub_llm(payload), audit_log=audit_fn,
    )
    assert "real rates" in [f.name for f in out.relevant_macro_factors]
    assert out.macro_regime_cited_chunk_ids == [rs[0].chunk_id]
    # The audited template_vars should record the rendered data_points string,
    # not the raw dict — confirms the orchestrator hand-off shape.
    rendered = captured[0]["payload"]["template_vars"]["data_points"]
    assert "DGS10" in rendered


async def test_uk_macro_agent_runs() -> None:
    rs = [_retrieval()]
    cid = str(rs[0].chunk_id)
    payload = {
        "uk_macro_context": "Bank Rate plateau; CPI moderating.",
        "bank_rate_context": "Bank Rate held at 4.50%.",
        "inflation_context": "Headline 2.8%, services sticky.",
        "sterling_or_rates_sensitivity": [
            {"name": "FX translation", "description": "GBP weakness lifts USD revenue", "cited_chunk_ids": [cid]},
        ],
        "relevant_data_points": {"BoE_BankRate": "Bank Rate, %"},
        "cited_chunk_ids": [cid],
        "notes": None,
    }
    captured, audit_fn = _capture_audit()
    out = await uk_macro_agent.run(
        "AZN.L", retrievals=rs, data_points={"BoE_BankRate": 4.50},
        llm_complete=_stub_llm(payload), audit_log=audit_fn,
    )
    assert "Bank Rate" in out.bank_rate_context
    assert captured[0]["actor"] == "uk_macro_agent"


async def test_valuation_agent_runs() -> None:
    rs = [_retrieval()]
    cid = str(rs[0].chunk_id)
    payload = {
        "valuation_summary": "Trades at a 12x P/E vs peer median 14x.",
        "peer_context": [
            {"peer": "XOM", "metric": "P/E NTM", "value": "13.5x", "cited_chunk_ids": [cid]},
        ],
        "valuation_flags": [
            {
                "description": "FX translation distorts reported margins",
                "severity": "watch", "cited_chunk_ids": [cid],
            },
        ],
        "missing_data": ["no consensus estimates available"],
        "unsourced_numbers": [],
        "summary_cited_chunk_ids": [cid],
        "notes": None,
    }
    captured, audit_fn = _capture_audit()
    out = await valuation_agent.run(
        "SHEL.L", retrievals=rs, llm_complete=_stub_llm(payload), audit_log=audit_fn,
    )
    assert out.peer_context[0].peer == "XOM"
    assert out.valuation_flags[0].severity == "watch"


async def test_thesis_tracker_runs_with_agent_summaries() -> None:
    rs = [_retrieval()]
    cid = str(rs[0].chunk_id)
    summaries = {
        "news": {"recent_events_count": 3, "high_severity_count": 0},
        "disclosure": {"risk_factor_count": 5},
        "macro": {"regime": "late cycle"},
    }
    payload = {
        "thesis_statement": (
            "Acme is positioned to grow given AI-compute demand, "
            "subject to a softening macro."
        ),
        "research_stance": "positive",
        "evidence_strength": 0.65,
        "key_pillars": [
            {"pillar": "AI compute demand", "rationale": "datacenter capex elevated", "cited_chunk_ids": [cid]},
        ],
        "disconfirming_evidence": [
            {"description": "guidance softness", "severity": "concern", "cited_chunk_ids": [cid]},
        ],
        "catalysts": [
            {"description": "Q3 print", "expected_window": "Q3 2026", "cited_chunk_ids": [cid]},
        ],
        "scorecard": [
            {"pillar": "AI compute demand", "score": 2, "rationale": "strong", "cited_chunk_ids": [cid]},
        ],
        "what_would_change_our_mind": [
            "datacenter capex rolling over",
            "loss of a top-3 customer",
        ],
        "statement_cited_chunk_ids": [cid],
        "notes": None,
    }
    captured, audit_fn = _capture_audit()
    out = await thesis_tracker_agent.run(
        "ACME", retrievals=rs, agent_summaries=summaries,
        focus_question="durability of demand?",
        llm_complete=_stub_llm(payload), audit_log=audit_fn,
    )
    assert out.research_stance == "positive"
    assert out.evidence_strength == 0.65
    rendered = captured[0]["payload"]["template_vars"]["agent_summaries"]
    assert "late cycle" in rendered
