"""End-to-end orchestrator tests with all external dependencies stubbed.

The orchestrator stitches together connectors, ingest, agents, and the
synthesizer. Rather than mock each individually at the module level, we use
the `Deps` injection point to swap in test stubs.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from services.api.agents.disclosure_agent import (
    DisclosureAgentOutput,
    DisclosureItem,
)
from services.api.agents.earnings_reviewer_agent import EarningsReviewerOutput
from services.api.agents.macro_agent import MacroAgentOutput, MacroFactor
from services.api.agents.market_research_agent import MarketResearchOutput, Peer
from services.api.agents.news_agent import NewsAgentOutput, NewsItem
from services.api.agents.price_agent import PriceAgentOutput
from services.api.agents.quant_validation_agent import QuantValidationOutput
from services.api.agents.synthesizer import CitedStatement, FinalDossier
from services.api.agents.thesis_tracker_agent import (
    ThesisPillar,
    ThesisTrackerOutput,
)
from services.api.agents.uk_macro_agent import UkMacroOutput
from services.api.agents.uk_rns_agent import RnsItem, UkRnsAgentOutput
from services.api.agents.valuation_agent import ValuationAgentOutput
from services.api.data._errors import MissingApiKeyError
from services.api.data._types import (
    PriceBar,
    PriceSeries,
    RawDocument,
    TimeSeries,
    TimeSeriesPoint,
)
from services.api.ingest._types import Chunk, Retrieval
from services.api.orchestrator import (
    Deps,
    ThesisOrchestrator,
    ThesisRunRequest,
)


# --------------- shared stubs ---------------


def _news_doc() -> RawDocument:
    return RawDocument(
        kind="news", provider="news_api",
        url="https://x", title="Acme posts strong Q3",
        text="Body of the article", metadata={},
    )


def _price_series(n: int = 120, *, ticker: str = "X") -> PriceSeries:
    today = date.today()
    bars = [
        PriceBar(
            date=today - timedelta(days=n - i),
            open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1_000,
        )
        for i in range(n)
    ]
    return PriceSeries(ticker=ticker, provider="yfinance", currency="USD", bars=bars)


def _fred_series(value: float | None = 4.5) -> TimeSeries:
    return TimeSeries(
        series_id="DGS10", provider="fred", name="10Y", units="%",
        points=[TimeSeriesPoint(date=date(2026, 5, 1), value=value)],
    )


# --------------- factory: a Deps with full happy-path stubs ---------------


def _make_happy_deps(*, region: str = "US") -> tuple[Deps, dict[str, list[Any]]]:
    """Return a Deps where every connector / agent / DB op is stubbed and
    a `calls` dict tracks invocations for assertions."""
    calls: dict[str, list[Any]] = {k: [] for k in [
        "audit", "create_thesis", "update_thesis", "insert_source",
        "insert_chunks", "insert_citation", "agents_run",
    ]}

    grounded_chunk_id = uuid4()
    source_id = uuid4()

    async def news_search(*args: Any, **kwargs: Any) -> list[RawDocument]:
        return [_news_doc()]

    async def fred_get_series(*args: Any, **kwargs: Any) -> TimeSeries:
        return _fred_series()

    async def sec_get_filings(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def rns_search(*args: Any, **kwargs: Any) -> list[RawDocument]:
        return [_news_doc().model_copy(update={"kind": "rns_proxy"})]

    async def ons_get_timeseries(*args: Any, **kwargs: Any) -> TimeSeries:
        return _fred_series(value=2.8).model_copy(update={"series_id": "L522"})

    async def prices_get(ticker: str, **kwargs: Any) -> PriceSeries:
        return _price_series(ticker=ticker)

    def chunk_document(doc: RawDocument, **kwargs: Any) -> list[Chunk]:
        return [Chunk(text=doc.text or doc.title or "x", chunk_index=0, token_count=10)]

    async def embed_documents(texts: list[str], **kwargs: Any) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]

    async def insert_source(thesis_id: UUID, doc: RawDocument, **kwargs: Any) -> UUID:
        calls["insert_source"].append((thesis_id, doc.kind))
        return source_id

    async def insert_chunks(sid: UUID, chunks: list[Chunk], embeddings: list[list[float]], **kwargs: Any) -> list[UUID]:
        calls["insert_chunks"].append((sid, len(chunks)))
        return [uuid4() for _ in chunks]

    async def retriever_search(query: str, **kwargs: Any) -> list[Retrieval]:
        return [
            Retrieval(
                chunk_id=grounded_chunk_id, source_id=source_id, text="news body",
                chunk_index=0, similarity=0.9, source_kind="news",
                source_provider="news_api", source_url=None,
                source_title="t", metadata={},
            )
        ]

    async def insert_citation(thesis_id, section, claim, chunk_ids, **kwargs):
        calls["insert_citation"].append((section, claim, list(chunk_ids)))
        return uuid4()

    async def audit_log(**kwargs: Any) -> UUID:
        calls["audit"].append(kwargs)
        return uuid4()

    async def create_thesis_row(*, thesis_id: UUID, **kwargs: Any) -> UUID:
        calls["create_thesis"].append(thesis_id)
        return thesis_id

    async def update_thesis_row(**kwargs: Any) -> None:
        calls["update_thesis"].append(kwargs)

    # ----- agent stubs -----

    def _track(name: str, output: Any):
        async def runner(*args: Any, **kwargs: Any) -> Any:
            calls["agents_run"].append(name)
            return output
        return runner

    news_run = _track("news_agent", NewsAgentOutput(
        recent_events=[NewsItem(summary="strong Q3", cited_chunk_ids=[grounded_chunk_id])],
    ))
    disclosure_run = _track("disclosure_agent", DisclosureAgentOutput(
        business_summary="Acme makes widgets.",
        business_summary_cited_chunk_ids=[grounded_chunk_id],
        key_disclosure_claims=[
            DisclosureItem(summary="top customer 15%", cited_chunk_ids=[grounded_chunk_id]),
        ],
    ))
    uk_rns_run = _track("uk_rns_agent", UkRnsAgentOutput(
        recent_rns_events=[RnsItem(summary="trading update", cited_chunk_ids=[grounded_chunk_id])],
    ))
    earnings_reviewer_run = _track("earnings_reviewer_agent", EarningsReviewerOutput(
        headline_read="beat-and-raise",
        headline_cited_chunk_ids=[grounded_chunk_id],
        management_tone="positive", thesis_impact="strengthens",
    ))
    market_research_run = _track("market_research_agent", MarketResearchOutput(
        sector="tech",
        sector_cited_chunk_ids=[grounded_chunk_id],
        market_structure="concentrated",
        market_structure_cited_chunk_ids=[grounded_chunk_id],
        peer_set=[Peer(name="MSFT", cited_chunk_ids=[grounded_chunk_id])],
    ))
    macro_run = _track("macro_agent", MacroAgentOutput(
        macro_regime="late cycle",
        macro_regime_cited_chunk_ids=[grounded_chunk_id],
        relevant_macro_factors=[
            MacroFactor(name="rates", description="elevated", cited_chunk_ids=[grounded_chunk_id]),
        ],
        data_points_used={"DGS10": "10Y, %"},
    ))
    uk_macro_run = _track("uk_macro_agent", UkMacroOutput(
        uk_macro_context="UK regime",
        bank_rate_context="held",
        inflation_context="moderating",
        cited_chunk_ids=[grounded_chunk_id],
    ))
    valuation_run = _track("valuation_agent", ValuationAgentOutput(
        valuation_summary="trades at 12x",
        summary_cited_chunk_ids=[grounded_chunk_id],
    ))
    thesis_tracker_run = _track("thesis_tracker_agent", ThesisTrackerOutput(
        thesis_statement="Acme positioned to grow",
        statement_cited_chunk_ids=[grounded_chunk_id],
        research_stance="positive", evidence_strength=0.7,
        key_pillars=[ThesisPillar(pillar="growth", rationale="r", cited_chunk_ids=[grounded_chunk_id])],
        what_would_change_our_mind=["loss of top customer"],
    ))
    synthesizer_run = _track("synthesizer", FinalDossier(
        executive_summary="Acme is positioned to grow.",
        executive_summary_cited_chunk_ids=[grounded_chunk_id],
        research_stance="positive", evidence_strength=0.7,
        bull_case=[CitedStatement(statement="growth", cited_chunk_ids=[grounded_chunk_id])],
        bear_case=[],
        catalysts=[CitedStatement(statement="Q3 print", cited_chunk_ids=[grounded_chunk_id])],
        key_risks=[],
        disconfirming_evidence=[],
        macro_context=None, valuation_summary=None,
        quant_summary="120 bars; vol n/a",
        limitations=[],
    ))
    price_run = _track("price_agent", PriceAgentOutput(
        summary="120 bars", bars_count=120, data_quality="good",
    ))
    quant_validation_run = _track("quant_validation_agent", QuantValidationOutput(
        available=True, summary="ok",
    ))

    deps = Deps(
        news_search=news_search,
        fred_get_series=fred_get_series,
        sec_get_filings=sec_get_filings,
        rns_search=rns_search,
        ons_get_timeseries=ons_get_timeseries,
        prices_get=prices_get,
        chunk_document=chunk_document,
        embed_documents=embed_documents,
        insert_source=insert_source,
        insert_chunks=insert_chunks,
        retriever_search=retriever_search,
        insert_citation=insert_citation,
        audit_log=audit_log,
        create_thesis_row=create_thesis_row,
        update_thesis_row=update_thesis_row,
        news_run=news_run,
        disclosure_run=disclosure_run,
        uk_rns_run=uk_rns_run,
        earnings_reviewer_run=earnings_reviewer_run,
        market_research_run=market_research_run,
        macro_run=macro_run,
        uk_macro_run=uk_macro_run,
        valuation_run=valuation_run,
        thesis_tracker_run=thesis_tracker_run,
        synthesizer_run=synthesizer_run,
        price_run=price_run,
        quant_validation_run=quant_validation_run,
        fred_series=("DGS10",),
        ons_series=(("MM23", "L522"),),
    )
    return deps, calls


# --------------- end-to-end happy-path tests ---------------


async def test_us_equity_full_run() -> None:
    deps, calls = _make_happy_deps(region="US")
    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="NVDA"))

    assert result.status == "completed"
    assert result.research_stance == "positive"
    assert 0.0 <= (result.evidence_strength or 0.0) <= 1.0
    assert result.dossier is not None
    assert result.errors == []

    # Section + thesis_tracker + synthesizer + price + quant agents fired.
    agents_run = calls["agents_run"]
    assert "news_agent" in agents_run
    assert "market_research_agent" in agents_run
    assert "macro_agent" in agents_run
    assert "valuation_agent" in agents_run
    assert "earnings_reviewer_agent" in agents_run
    assert "price_agent" in agents_run
    assert "quant_validation_agent" in agents_run
    assert "thesis_tracker_agent" in agents_run
    assert "synthesizer" in agents_run
    # UK-only agents must not run for a US ticker.
    assert "uk_rns_agent" not in agents_run
    assert "uk_macro_agent" not in agents_run

    # Thesis row created at start and updated at end.
    assert len(calls["create_thesis"]) == 1
    assert len(calls["update_thesis"]) == 1
    assert calls["update_thesis"][0]["status"] == "completed"

    # At least one source persisted (news), and citations stored.
    assert result.sources_persisted >= 1
    assert result.chunks_persisted >= 1
    assert result.citations_persisted >= 1

    # Audit run_started + run_finished bookend.
    actions = [c["action"] for c in calls["audit"]]
    assert actions[0] == "run_started"
    assert "run_finished" in actions


async def test_uk_equity_runs_uk_specific_agents() -> None:
    deps, calls = _make_happy_deps(region="UK")
    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="SHEL.L"))

    assert result.status == "completed"
    assert result.instrument.region == "UK"

    agents_run = calls["agents_run"]
    assert "uk_rns_agent" in agents_run
    assert "uk_macro_agent" in agents_run


async def test_etf_skips_disclosure_and_uk_rns() -> None:
    deps, calls = _make_happy_deps()
    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="SPY"))

    assert result.status == "completed"
    assert result.instrument.asset_class == "etf"
    agents_run = calls["agents_run"]
    assert "disclosure_agent" not in agents_run
    assert "uk_rns_agent" not in agents_run


# --------------- failure-mode tests ---------------


async def test_missing_news_api_key_does_not_abort_run() -> None:
    deps, calls = _make_happy_deps()

    async def failing_news(*args: Any, **kwargs: Any) -> list[RawDocument]:
        raise MissingApiKeyError("NEWS_API_KEY", provider="news_api")

    deps.news_search = failing_news
    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="NVDA"))

    # Synthesizer still ran with reduced inputs; dossier produced.
    assert result.status == "completed"
    # An error was recorded.
    assert any(e.actor == "news_api" for e in result.errors)


async def test_synthesizer_failure_marks_run_failed_but_audits_and_updates() -> None:
    deps, calls = _make_happy_deps()

    async def failing_synth(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("synth boom")

    deps.synthesizer_run = failing_synth
    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="NVDA"))

    assert result.status == "failed"
    assert result.dossier is None
    assert calls["update_thesis"][0]["status"] == "failed"
    assert any("synth boom" in e.message for e in result.errors)


async def test_invalid_ticker_raises() -> None:
    orch = ThesisOrchestrator()
    with pytest.raises(ValueError, match="Invalid ticker"):
        await orch.run(ThesisRunRequest(ticker="not a ticker!"))


async def test_uses_request_thesis_id_when_provided() -> None:
    deps, calls = _make_happy_deps()
    fixed = uuid4()
    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="NVDA", thesis_id=fixed))
    assert result.thesis_id == fixed
    assert calls["create_thesis"][0] == fixed


async def test_section_agent_failure_does_not_abort_run() -> None:
    deps, calls = _make_happy_deps()

    async def failing_news_agent(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("news boom")

    deps.news_run = failing_news_agent
    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="NVDA"))

    assert result.status == "completed"
    assert any(e.actor == "news_agent" for e in result.errors)
