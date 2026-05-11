from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, Field

from services.api import config
from services.api.agents._base import run_agent
from services.api.ingest._types import Retrieval
from services.api import llm


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    config.get_settings.cache_clear()


class _Item(BaseModel):
    summary: str
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


class _AgentOut(BaseModel):
    items: list[_Item] = Field(default_factory=list)
    cited_chunk_ids: list[UUID] = Field(default_factory=list)


def _retrieval(text: str = "x") -> Retrieval:
    return Retrieval(
        chunk_id=uuid4(),
        source_id=uuid4(),
        text=text,
        chunk_index=0,
        similarity=0.8,
        source_kind="news",
        source_provider="news_api",
        source_url=None,
        source_title=None,
        metadata={},
    )


async def test_run_agent_filters_unknown_chunk_ids_at_top_level_and_nested() -> None:
    rs = [_retrieval(), _retrieval()]
    valid_ids = [r.chunk_id for r in rs]
    bogus = uuid4()

    audit_calls: list[dict] = []

    async def fake_audit(**kwargs):
        audit_calls.append(kwargs)
        return uuid4()

    async def fake_llm(request: llm.LLMRequest, schema):
        # Simulate the model emitting one valid + one bogus chunk_id at every level.
        out = _AgentOut(
            items=[
                _Item(summary="real", cited_chunk_ids=[valid_ids[0], bogus]),
                _Item(summary="dup", cited_chunk_ids=[valid_ids[1], valid_ids[1]]),
            ],
            cited_chunk_ids=[valid_ids[0], bogus, valid_ids[1]],
        )
        resp = llm.LLMResponse(
            text="...", parsed=None, model="claude-sonnet-4-6",
            input_tokens=10, output_tokens=5, latency_ms=100,
            cost_usd=0.001,
        )
        return out, resp

    out = await run_agent(
        agent_name="news_agent",
        prompt_name="news",
        output_schema=_AgentOut,
        retrievals=rs,
        template_vars={"ticker": "NVDA"},
        llm_complete=fake_llm,
        audit_log=fake_audit,
    )

    assert out.cited_chunk_ids == [valid_ids[0], valid_ids[1]]  # bogus dropped
    assert out.items[0].cited_chunk_ids == [valid_ids[0]]      # bogus dropped
    assert out.items[1].cited_chunk_ids == [valid_ids[1]]      # dedup
    assert audit_calls and audit_calls[0]["status"] == "ok"
    assert audit_calls[0]["actor"] == "news_agent"
    assert audit_calls[0]["model"] == "claude-sonnet-4-6"
    # context shouldn't appear in audited template_vars (too noisy).
    assert "context" not in audit_calls[0]["payload"]["template_vars"]


async def test_run_agent_drops_items_with_no_supporting_chunks() -> None:
    """Items whose cited_chunk_ids becomes empty after filtering must be removed
    entirely, not retained as unsupported claims."""
    rs = [_retrieval(), _retrieval()]
    valid_ids = [r.chunk_id for r in rs]
    bogus = uuid4()

    captured_payloads: list[dict] = []

    async def fake_audit(**kwargs):
        captured_payloads.append(kwargs["payload"])
        return uuid4()

    async def fake_llm(request: llm.LLMRequest, schema):
        out = _AgentOut(
            items=[
                _Item(summary="real claim", cited_chunk_ids=[valid_ids[0]]),
                _Item(summary="hallucinated", cited_chunk_ids=[bogus]),
                _Item(summary="another real", cited_chunk_ids=[valid_ids[1], bogus]),
            ],
            cited_chunk_ids=[valid_ids[0]],
        )
        resp = llm.LLMResponse(
            text="...", parsed=None, model="claude-sonnet-4-6",
            input_tokens=10, output_tokens=5, latency_ms=100, cost_usd=0.001,
            raw={"tool_input": {"items": "..."}},
        )
        return out, resp

    out = await run_agent(
        agent_name="news_agent",
        prompt_name="news",
        output_schema=_AgentOut,
        retrievals=rs,
        template_vars={"ticker": "X"},
        llm_complete=fake_llm,
        audit_log=fake_audit,
    )

    assert [item.summary for item in out.items] == ["real claim", "another real"]
    # The dropped item's bogus UUID also doesn't survive at the surviving items.
    assert all(item.cited_chunk_ids for item in out.items)


async def test_run_agent_audits_raw_model_output_separately() -> None:
    """Audit payload must include both the filtered output and the model's raw
    tool input so post-filter behaviour is reconstructible from the audit row."""
    rs = [_retrieval()]
    valid = rs[0].chunk_id
    bogus = uuid4()

    captured: list[dict] = []

    async def fake_audit(**kwargs):
        captured.append(kwargs["payload"])
        return uuid4()

    raw_blob = {
        "tool_name": "submit_analysis",
        "tool_input": {
            "items": [
                {"summary": "kept", "cited_chunk_ids": [str(valid)]},
                {"summary": "dropped", "cited_chunk_ids": [str(bogus)]},
            ],
            "cited_chunk_ids": [str(valid), str(bogus)],
        },
        "model": "claude-sonnet-4-6",
    }

    async def fake_llm(request: llm.LLMRequest, schema):
        out = _AgentOut(
            items=[
                _Item(summary="kept", cited_chunk_ids=[valid]),
                _Item(summary="dropped", cited_chunk_ids=[bogus]),
            ],
            cited_chunk_ids=[valid, bogus],
        )
        resp = llm.LLMResponse(
            text="...", parsed=None, model="claude-sonnet-4-6",
            input_tokens=10, output_tokens=5, latency_ms=100,
            cost_usd=0.001,
            raw=raw_blob,
        )
        return out, resp

    await run_agent(
        agent_name="news_agent",
        prompt_name="news",
        output_schema=_AgentOut,
        retrievals=rs,
        template_vars={"ticker": "X"},
        llm_complete=fake_llm,
        audit_log=fake_audit,
    )

    payload = captured[0]
    # Filtered output reflects the post-processing.
    filtered_summaries = [it["summary"] for it in payload["output"]["items"]]
    assert filtered_summaries == ["kept"]
    # Raw output captures what the model actually emitted before filtering.
    assert "output_raw" in payload
    raw_summaries = [it["summary"] for it in payload["output_raw"]["tool_input"]["items"]]
    assert raw_summaries == ["kept", "dropped"]


async def test_run_agent_audits_failure_then_reraises() -> None:
    audit_calls: list[dict] = []

    async def fake_audit(**kwargs):
        audit_calls.append(kwargs)
        return uuid4()

    async def fake_llm(request, schema):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await run_agent(
            agent_name="news_agent",
            prompt_name="news",
            output_schema=_AgentOut,
            retrievals=[],
            template_vars={"ticker": "X"},
            llm_complete=fake_llm,
            audit_log=fake_audit,
        )

    assert audit_calls and audit_calls[0]["status"] == "error"
    assert "boom" in audit_calls[0]["payload"]["error"]
