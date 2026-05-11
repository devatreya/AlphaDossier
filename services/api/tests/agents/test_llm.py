from __future__ import annotations

import pytest
from pydantic import BaseModel

from services.api import config, llm
from services.api.data._errors import MissingApiKeyError

from .conftest import FakeAnthropic, FakeContentBlock, FakeMessage, FakeUsage


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    config.get_settings.cache_clear()


class _Out(BaseModel):
    headline: str
    score: float


async def test_complete_structured_extracts_tool_use(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    fake = FakeAnthropic.with_tool_use(
        {"headline": "Revenue beat", "score": 0.85},
        model="claude-sonnet-4-6",
        input_tokens=200, output_tokens=80,
    )
    req = llm.LLMRequest(
        model="claude-sonnet-4-6", system="be a thing", user="data here",
    )
    obj, resp = await llm.complete_structured(req, _Out, client=fake)  # type: ignore[arg-type]

    assert obj.headline == "Revenue beat"
    assert obj.score == 0.85
    assert resp.input_tokens == 200
    assert resp.output_tokens == 80
    assert resp.cost_usd is not None and resp.cost_usd > 0
    assert resp.parsed == {"headline": "Revenue beat", "score": 0.85}

    sent = fake.messages.last_kwargs
    assert sent["tool_choice"] == {"type": "tool", "name": "submit_analysis"}
    assert sent["tools"][0]["name"] == "submit_analysis"
    assert sent["temperature"] == 0.0


async def test_complete_structured_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    req = llm.LLMRequest(model="x", system="s", user="u")
    with pytest.raises(MissingApiKeyError):
        await llm.complete_structured(req, _Out)


async def test_complete_structured_raises_when_no_tool_use(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the model emits text instead of calling the tool we surface that
    immediately rather than silently producing a junk Pydantic object."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    msg = FakeMessage(
        content=[FakeContentBlock(type="text", text="hi")],
        usage=FakeUsage(0, 0),
    )
    fake = FakeAnthropic(messages=type(FakeAnthropic.with_tool_use({}).messages)(response=msg))
    req = llm.LLMRequest(model="x", system="s", user="u")
    with pytest.raises(llm.LLMError):
        await llm.complete_structured(req, _Out, client=fake)  # type: ignore[arg-type]


def test_estimate_cost_unknown_model_returns_none() -> None:
    assert llm.estimate_cost_usd("some-other-model", 1000, 1000) is None


def test_estimate_cost_known_models() -> None:
    haiku_cost = llm.estimate_cost_usd("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    sonnet_cost = llm.estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000)
    opus_cost = llm.estimate_cost_usd("claude-opus-4-7", 1_000_000, 1_000_000)
    assert haiku_cost is not None
    assert sonnet_cost is not None
    assert opus_cost is not None
    # Cost should rise with capability tier.
    assert haiku_cost < sonnet_cost < opus_cost


async def test_complete_structured_closes_internal_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the wrapper creates the AsyncAnthropic itself, it must close it
    after use so the underlying httpx pool isn't leaked across agent runs."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

    fake = FakeAnthropic.with_tool_use({"headline": "ok", "score": 0.5})
    closed = {"called": False}

    async def fake_close() -> None:
        closed["called"] = True

    fake.close = fake_close  # type: ignore[attr-defined]

    monkeypatch.setattr(llm, "_get_client", lambda: fake)

    req = llm.LLMRequest(model="claude-sonnet-4-6", system="s", user="u")
    await llm.complete_structured(req, _Out)  # no client= => internal client path

    assert closed["called"] is True


async def test_complete_structured_does_not_close_injected_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper is non-owning when the caller passes in a client, so close()
    is left to the caller — otherwise long-lived clients (orchestrators) would
    have their connection pool yanked out from under them."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

    fake = FakeAnthropic.with_tool_use({"headline": "ok", "score": 0.5})
    closed = {"called": False}

    async def fake_close() -> None:
        closed["called"] = True

    fake.close = fake_close  # type: ignore[attr-defined]

    req = llm.LLMRequest(model="claude-sonnet-4-6", system="s", user="u")
    await llm.complete_structured(req, _Out, client=fake)  # type: ignore[arg-type]

    assert closed["called"] is False


async def test_complete_structured_populates_raw_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    fake = FakeAnthropic.with_tool_use(
        {"headline": "Hi", "score": 0.7}, model="claude-sonnet-4-6",
    )
    req = llm.LLMRequest(model="claude-sonnet-4-6", system="s", user="u")
    _, resp = await llm.complete_structured(req, _Out, client=fake)  # type: ignore[arg-type]

    assert resp.raw["tool_name"] == "submit_analysis"
    assert resp.raw["tool_input"] == {"headline": "Hi", "score": 0.7}
    assert resp.raw["model"] == "claude-sonnet-4-6"


async def test_complete_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    fake = FakeAnthropic.with_text("a paragraph of synthesis prose")
    req = llm.LLMRequest(model="claude-opus-4-7", system="s", user="u")
    resp = await llm.complete(req, client=fake)  # type: ignore[arg-type]
    assert "synthesis prose" in resp.text
    assert resp.parsed is None
