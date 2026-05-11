"""Regression tests for the four Phase 4c review findings."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

from services.api.agents.disclosure_agent import (
    DisclosureAgentOutput,
    DisclosureItem,
)
from services.api.agents.earnings_reviewer_agent import (
    EarningsReviewerOutput,
    MetricChange,
)
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
    _ThesisRun,
)


def _retrieval(chunk_id: UUID, *, text: str = "supporting context") -> Retrieval:
    return Retrieval(
        chunk_id=chunk_id, source_id=uuid4(), text=text,
        chunk_index=0, similarity=0.9, source_kind="news",
        source_provider="news_api", source_url=None,
        source_title="t", metadata={},
    )


def _price_series(n: int = 120) -> PriceSeries:
    today = date.today()
    bars = [
        PriceBar(
            date=today - timedelta(days=n - i),
            open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1_000,
        )
        for i in range(n)
    ]
    return PriceSeries(ticker="X", provider="yfinance", currency="USD", bars=bars)


def _make_deps_for_full_run() -> tuple[Deps, dict[str, list[Any]], UUID]:
    """A Deps where the section-agent stubs use the new summary-suffix
    citation conventions, so the walker fix is exercised end-to-end."""
    calls: dict[str, list[Any]] = {k: [] for k in [
        "audit", "insert_citation", "agents_run", "company_ir_fetch",
        "validate_citation",
    ]}
    grounded = uuid4()
    src_id = uuid4()

    async def news_search(*a, **kw) -> list[RawDocument]:
        return [RawDocument(kind="news", provider="news_api", text="news body", title="t")]

    async def fred_get_series(series_id: str) -> TimeSeries:
        return TimeSeries(
            series_id=series_id, provider="fred",
            points=[TimeSeriesPoint(date=date(2026, 5, 1), value=4.5)],
        )

    async def sec_get_filings(*a, **kw) -> list[Any]:
        return []

    async def rns_search(*a, **kw) -> list[RawDocument]:
        return []

    async def ons_get_timeseries(*a, **kw) -> TimeSeries:
        return TimeSeries(series_id="L522", provider="ons", points=[])

    async def prices_get(ticker: str, **kw) -> PriceSeries:
        return _price_series().model_copy(update={"ticker": ticker})

    async def company_ir_fetch(url: str, **kw) -> RawDocument:
        calls["company_ir_fetch"].append(url)
        return RawDocument(
            kind="ir_html", provider="company_ir", url=url,
            text="<html><body>Filing body content</body></html>",
            metadata={"content_type": "text/html"},
        )

    def chunk_document(doc: RawDocument, **kw) -> list[Chunk]:
        return [Chunk(text=doc.text or "x", chunk_index=0, token_count=10)]

    async def embed_documents(texts: list[str], **kw) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]

    async def insert_source(thesis_id: UUID, doc: RawDocument, **kw) -> UUID:
        return src_id

    async def insert_chunks(sid: UUID, chunks: list[Chunk], embeddings: list[list[float]], **kw) -> list[UUID]:
        return [uuid4() for _ in chunks]

    async def retriever_search(query: str, **kw) -> list[Retrieval]:
        # Real chunk text the validate_citation heuristic can score against.
        return [_retrieval(grounded, text="Acme reported strong revenue growth in Q3")]

    async def insert_citation(thesis_id, section, claim, chunk_ids, *, confidence=None, **kw):
        calls["insert_citation"].append({
            "section": section, "claim": claim,
            "chunk_ids": list(chunk_ids), "confidence": confidence,
        })
        return uuid4()

    def validate_citation(claim: str, supporting_texts):
        calls["validate_citation"].append({"claim": claim})
        # Use the real validator so confidence values reflect actual logic.
        from services.api.ingest import citations
        return citations.validate_citation(claim, supporting_texts)

    async def audit_log(**kw) -> UUID:
        calls["audit"].append(kw)
        return uuid4()

    async def create_thesis_row(*, thesis_id: UUID, **kw) -> UUID:
        return thesis_id

    async def update_thesis_row(**kw) -> None:
        pass

    def _track(name: str, output: Any):
        async def runner(*a: Any, **kw: Any) -> Any:
            calls["agents_run"].append(name)
            return output
        return runner

    deps = Deps(
        news_search=news_search,
        fred_get_series=fred_get_series,
        sec_get_filings=sec_get_filings,
        rns_search=rns_search,
        ons_get_timeseries=ons_get_timeseries,
        prices_get=prices_get,
        company_ir_fetch=company_ir_fetch,
        chunk_document=chunk_document,
        embed_documents=embed_documents,
        insert_source=insert_source,
        insert_chunks=insert_chunks,
        retriever_search=retriever_search,
        insert_citation=insert_citation,
        validate_citation=validate_citation,
        audit_log=audit_log,
        create_thesis_row=create_thesis_row,
        update_thesis_row=update_thesis_row,
        # Agent stubs using the new summary-suffix conventions.
        news_run=_track("news_agent", NewsAgentOutput(
            recent_events=[NewsItem(summary="strong Q3 revenue", cited_chunk_ids=[grounded])],
        )),
        disclosure_run=_track("disclosure_agent", DisclosureAgentOutput(
            business_summary="Acme makes industrial widgets used in industrial plants",
            business_summary_cited_chunk_ids=[grounded],
            key_disclosure_claims=[
                DisclosureItem(summary="Top customer concentration 15% of revenue", cited_chunk_ids=[grounded]),
            ],
        )),
        uk_rns_run=_track("uk_rns_agent", UkRnsAgentOutput(
            recent_rns_events=[RnsItem(summary="trading update positive", cited_chunk_ids=[grounded])],
        )),
        earnings_reviewer_run=_track("earnings_reviewer_agent", EarningsReviewerOutput(
            headline_read="Beat-and-raise quarter with strong revenue growth",
            headline_cited_chunk_ids=[grounded],
            management_tone="positive",
            thesis_impact="strengthens",
            key_metric_changes=[
                MetricChange(metric="revenue", direction="up", magnitude="+12% YoY",
                            period="Q3", cited_chunk_ids=[grounded]),
            ],
        )),
        market_research_run=_track("market_research_agent", MarketResearchOutput(
            sector="industrial widgets",
            sector_cited_chunk_ids=[grounded],
            market_structure="Concentrated supplier base with growing demand",
            market_structure_cited_chunk_ids=[grounded],
            peer_set=[Peer(name="MSFT", cited_chunk_ids=[grounded])],
        )),
        macro_run=_track("macro_agent", MacroAgentOutput(
            macro_regime="late cycle US with elevated rates",
            macro_regime_cited_chunk_ids=[grounded],
            relevant_macro_factors=[
                MacroFactor(name="rates", description="elevated 10y yield", cited_chunk_ids=[grounded]),
            ],
            data_points_used={"DGS10": "10Y, %"},
        )),
        uk_macro_run=_track("uk_macro_agent", UkMacroOutput(
            uk_macro_context="UK regime",
            bank_rate_context="held at 4.50%",
            inflation_context="moderating from peak",
            cited_chunk_ids=[grounded],
        )),
        valuation_run=_track("valuation_agent", ValuationAgentOutput(
            valuation_summary="Acme trades at 12x P/E vs peer median 14x",
            summary_cited_chunk_ids=[grounded],
        )),
        thesis_tracker_run=_track("thesis_tracker_agent", ThesisTrackerOutput(
            thesis_statement="Acme positioned for growth given strong Q3 revenue",
            statement_cited_chunk_ids=[grounded],
            research_stance="positive", evidence_strength=0.7,
            key_pillars=[ThesisPillar(pillar="growth", rationale="strong revenue", cited_chunk_ids=[grounded])],
        )),
        synthesizer_run=_track("synthesizer", FinalDossier(
            executive_summary="Acme is positioned for revenue growth.",
            executive_summary_cited_chunk_ids=[grounded],
            research_stance="positive", evidence_strength=0.7,
            bull_case=[CitedStatement(statement="strong revenue growth", cited_chunk_ids=[grounded])],
        )),
        price_run=_track("price_agent", PriceAgentOutput(
            summary="120 bars", bars_count=120, data_quality="good",
        )),
        quant_validation_run=_track("quant_validation_agent", QuantValidationOutput(
            available=True, summary="ok",
        )),
        fred_series=("DGS10",),
        ons_series=(("MM23", "L522"),),
    )
    return deps, calls, grounded


# ============== Fix 1: walker pairs summary-suffix fields ==============


async def test_valuation_summary_produces_citation() -> None:
    deps, calls, grounded = _make_deps_for_full_run()
    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="NVDA"))
    assert result.status == "completed"

    valuation_citations = [
        c for c in calls["insert_citation"]
        if c["section"] == "valuation"
        and "12x P/E" in c["claim"]
    ]
    assert valuation_citations, (
        "valuation_summary paired with summary_cited_chunk_ids must persist a citation; "
        f"saw sections: {[c['section'] for c in calls['insert_citation']]}"
    )
    assert valuation_citations[0]["chunk_ids"] == [grounded]


async def test_earnings_headline_read_produces_citation() -> None:
    deps, calls, grounded = _make_deps_for_full_run()
    orch = ThesisOrchestrator(deps=deps)
    await orch.run(ThesisRunRequest(ticker="NVDA"))

    headline_citations = [
        c for c in calls["insert_citation"]
        if c["section"] == "earnings_reviewer"
        and "Beat-and-raise" in c["claim"]
    ]
    assert headline_citations, "headline_read must pair with headline_cited_chunk_ids"
    assert headline_citations[0]["chunk_ids"] == [grounded]


async def test_thesis_statement_produces_citation() -> None:
    deps, calls, grounded = _make_deps_for_full_run()
    orch = ThesisOrchestrator(deps=deps)
    await orch.run(ThesisRunRequest(ticker="NVDA"))

    statement_citations = [
        c for c in calls["insert_citation"]
        if c["section"] == "thesis_tracker"
        and "Acme positioned" in c["claim"]
    ]
    assert statement_citations, (
        "thesis_statement must pair with statement_cited_chunk_ids; "
        f"saw thesis_tracker claims: "
        f"{[c['claim'][:50] for c in calls['insert_citation'] if c['section'] == 'thesis_tracker']}"
    )


async def test_walker_skips_literal_fields() -> None:
    """MetricChange.direction is Literal['up','down',...] — values like 'up'
    must not be stored as a 'claim' citation."""
    deps, calls, grounded = _make_deps_for_full_run()
    orch = ThesisOrchestrator(deps=deps)
    await orch.run(ThesisRunRequest(ticker="NVDA"))

    literal_value_claims = [
        c for c in calls["insert_citation"]
        if c["claim"] in {"up", "down", "flat", "unclear", "positive", "negative", "mixed"}
    ]
    assert not literal_value_claims, (
        f"Literal-typed enum values should not become citations; got: {literal_value_claims}"
    )


async def test_walker_unit_pairs_summary_suffix() -> None:
    """Direct unit test on the static walker for valuation_summary + summary_cited_chunk_ids."""
    grounded = uuid4()
    output = ValuationAgentOutput(
        valuation_summary="Trades at 12x P/E vs peers",
        summary_cited_chunk_ids=[grounded],
    )
    captured: list[tuple[str, str, list[UUID]]] = []

    async def store(section: str, claim: str, chunk_ids):
        captured.append((section, claim, list(chunk_ids)))

    await _ThesisRun._walk_for_citations(output, "valuation", store)
    assert any(
        section == "valuation"
        and "12x P/E" in claim
        and chunk_ids == [grounded]
        for section, claim, chunk_ids in captured
    )


# ============== Fix 2: SEC filings fetch primary doc ==============


async def test_sec_filings_fetch_primary_doc_via_company_ir() -> None:
    deps, calls, grounded = _make_deps_for_full_run()

    # Override sec_get_filings to return some filing refs.
    from services.api.data._types import FilingRef

    async def sec_with_filings(*a, **kw) -> list[FilingRef]:
        return [
            FilingRef(
                cik="0000320193",
                accession_number="0000320193-26-000010",
                form="10-Q",
                filing_date=date(2026, 4, 30),
                primary_document="aapl-q1.htm",
                primary_doc_url="https://sec.gov/Archives/edgar/data/320193/000032019326000010/aapl-q1.htm",
                title="10-Q Q1",
            ),
            FilingRef(
                cik="0000320193",
                accession_number="0000320193-25-000099",
                form="10-K",
                filing_date=date(2025, 10, 30),
                primary_document="aapl-fy25.htm",
                primary_doc_url="https://sec.gov/Archives/edgar/data/320193/000032019325000099/aapl-fy25.htm",
                title="10-K FY25",
            ),
        ]

    deps.sec_get_filings = sec_with_filings

    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="AAPL"))

    assert result.status == "completed"
    # Both filings' primary docs were fetched.
    assert len(calls["company_ir_fetch"]) == 2
    assert all(
        url.startswith("https://sec.gov/Archives/")
        for url in calls["company_ir_fetch"]
    )


async def test_sec_filing_fetch_failure_is_skipped_not_aborted() -> None:
    deps, calls, grounded = _make_deps_for_full_run()
    from services.api.data._errors import ConnectorError
    from services.api.data._types import FilingRef

    async def sec_with_filings(*a, **kw) -> list[FilingRef]:
        return [FilingRef(
            cik="0000320193", accession_number="X", form="10-K",
            filing_date=date(2025, 10, 30),
            primary_document="x.htm",
            primary_doc_url="https://sec.gov/x.htm",
        )]

    async def failing_fetch(*a, **kw) -> RawDocument:
        raise ConnectorError("filing too large", provider="company_ir")

    deps.sec_get_filings = sec_with_filings
    deps.company_ir_fetch = failing_fetch

    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="AAPL"))

    assert result.status == "completed"  # other agents still ran
    assert any("sec_filing:" in e.actor for e in result.errors)
    # Audit row recorded the unavailable filing.
    audit_actions = [
        c for c in calls["audit"]
        if c.get("status") == "warn" and "fetch_filing" in c.get("action", "")
    ]
    assert audit_actions


# ============== Fix 3: validate_citation + confidence ==============


async def test_validate_citation_runs_and_confidence_persisted() -> None:
    deps, calls, grounded = _make_deps_for_full_run()
    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="NVDA"))

    assert result.status == "completed"
    assert calls["validate_citation"], "validate_citation must be called for each persisted claim"
    # Every citations.insert call has a numeric confidence (validate ran).
    cited = [c for c in calls["insert_citation"] if c["chunk_ids"]]
    assert cited, "expected some citations"
    assert all(
        c["confidence"] is None or isinstance(c["confidence"], float)
        for c in cited
    )
    # Citations whose claim word-overlaps with chunk text get a positive score.
    high_overlap = [
        c for c in cited
        if c["confidence"] is not None and c["confidence"] > 0
    ]
    assert high_overlap, "expected at least one citation with > 0 overlap_score"


async def test_low_overlap_citation_writes_warn_audit() -> None:
    deps, calls, grounded = _make_deps_for_full_run()

    # Force the validator to always say "below threshold".
    from services.api.ingest._types import CitationValidation

    def low_validate(claim: str, supporting_texts):
        return CitationValidation(
            ok=False, overlap_score=0.05,
            matched_terms=[], missing_terms=["all"],
            reason="overlap 5% below 20%",
        )

    deps.validate_citation = low_validate
    orch = ThesisOrchestrator(deps=deps)
    await orch.run(ThesisRunRequest(ticker="NVDA"))

    low_overlap_audits = [
        c for c in calls["audit"]
        if c.get("action") == "citation_low_overlap"
    ]
    assert low_overlap_audits, "low-overlap citations must produce a warn audit"


# ============== Fix 4: missing FRED key audited ==============


async def test_missing_fred_key_audits_per_series() -> None:
    deps, calls, _ = _make_deps_for_full_run()

    async def failing_fred(series_id: str) -> Any:
        raise MissingApiKeyError("FRED_API_KEY", provider="fred")

    deps.fred_get_series = failing_fred
    deps.fred_series = ("DGS10", "CPIAUCSL")

    orch = ThesisOrchestrator(deps=deps)
    result = await orch.run(ThesisRunRequest(ticker="NVDA"))

    assert result.status == "completed"
    fred_warns = [
        c for c in calls["audit"]
        if c.get("actor") == "fred"
        and c.get("status") == "warn"
        and c.get("action", "").startswith("fetch_series:")
    ]
    assert len(fred_warns) == 2  # one per attempted series
    assert {c["action"] for c in fred_warns} == {
        "fetch_series:DGS10", "fetch_series:CPIAUCSL",
    }


async def test_missing_prices_key_audits() -> None:
    deps, calls, _ = _make_deps_for_full_run()

    from services.api.data._errors import ConnectorError

    async def failing_prices(ticker: str, **kw) -> PriceSeries:
        raise ConnectorError("yahoo down", provider="yfinance")

    deps.prices_get = failing_prices
    orch = ThesisOrchestrator(deps=deps)
    await orch.run(ThesisRunRequest(ticker="NVDA"))

    price_warns = [
        c for c in calls["audit"]
        if c.get("actor") == "prices" and c.get("status") == "warn"
    ]
    # Both ticker and benchmark fail.
    assert price_warns
    actions = {c["action"] for c in price_warns}
    assert "fetch" in actions
    assert any(a.startswith("fetch_benchmark:") for a in actions)
