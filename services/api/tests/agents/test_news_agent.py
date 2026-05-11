from __future__ import annotations

from uuid import uuid4

from services.api import llm
from services.api.agents import news_agent
from services.api.ingest._types import Retrieval


def _r() -> Retrieval:
    return Retrieval(
        chunk_id=uuid4(), source_id=uuid4(),
        text="Some news content", chunk_index=0,
        similarity=0.9, source_kind="news", source_provider="news_api",
        source_url=None, source_title=None, metadata={},
    )


async def test_news_agent_runs_through_stub_llm() -> None:
    rs = [_r(), _r()]

    async def fake_llm(request: llm.LLMRequest, schema):
        # Emit one valid item to confirm the pipeline preserves nested cited_chunk_ids.
        payload = {
            "recent_events": [
                {"summary": "Acme reported Q3", "cited_chunk_ids": [str(rs[0].chunk_id)]},
            ],
            "high_severity_news": [],
            "regulatory_or_legal_items": [],
            "sector_readthrough": [],
            "notes": None,
        }
        out = schema.model_validate(payload)
        resp = llm.LLMResponse(
            text="ok", parsed=None, model="claude-sonnet-4-6",
            input_tokens=50, output_tokens=20, latency_ms=200,
            cost_usd=0.001,
        )
        return out, resp

    audit_calls: list[dict] = []

    async def fake_audit(**kwargs):
        audit_calls.append(kwargs)
        return uuid4()

    out = await news_agent.run(
        "NVDA", retrievals=rs, llm_complete=fake_llm, audit_log=fake_audit,
    )
    assert len(out.recent_events) == 1
    assert out.recent_events[0].cited_chunk_ids == [rs[0].chunk_id]
    assert audit_calls[0]["actor"] == "news_agent"
