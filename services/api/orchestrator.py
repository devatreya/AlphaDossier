"""Thesis run orchestrator.

Wires Phase 2 connectors, Phase 3 ingest, and Phase 4 agents into a single
end-to-end flow:

  resolve identifier
    -> fetch sources (parallel; per-connector failures don't abort the run)
    -> persist sources, chunk + embed, store chunks (one Voyage batch)
    -> retrieve per-agent slices and run section agents (parallel)
    -> compute price + quant validation (no LLM)
    -> run thesis_tracker (gets section summaries)
    -> run synthesizer (gets all outputs)
    -> persist citations + final theses row

Every dependency is overridable via `Deps` so the whole flow can be tested
without a database, network, or API keys. The default Deps wires the real
implementations.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, Sequence
from uuid import UUID, uuid4

import asyncpg
from pydantic import BaseModel, Field

from . import audit
from .agents import (
    disclosure_agent,
    earnings_reviewer_agent,
    macro_agent,
    market_research_agent,
    news_agent,
    price_agent,
    quant_validation_agent,
    synthesizer,
    thesis_tracker_agent,
    uk_macro_agent,
    uk_rns_agent,
    valuation_agent,
)
from .data import (
    company_ir,
    fred,
    identifiers,
    news_api,
    ons,
    prices,
    sec_edgar,
    uk_rns,
)
from .data._errors import ConnectorError, MissingApiKeyError
from .data._types import Instrument, PriceSeries, RawDocument
from .db import acquire, get_pool
from .ingest import chunker, citations, document_store, embedder, retriever
from .ingest._types import Chunk, Retrieval

log = logging.getLogger(__name__)

# Default series snapshots for the macro agents. Tunable per deployment.
_DEFAULT_FRED_SERIES: tuple[str, ...] = ("DGS10", "DGS2", "CPIAUCSL", "UNRATE")
_DEFAULT_ONS_SERIES: tuple[tuple[str, str], ...] = (
    ("MM23", "L522"),  # CPIH all items
    ("UKEA", "ABMI"),  # GDP at market prices
)

# How far back to look for news / RNS items. 90 days matches NewsAPI free tier.
_NEWS_WINDOW_DAYS = 90
# Roughly 18 months of price history is enough for vol + drawdown + 1y returns.
_PRICE_WINDOW_DAYS = 540

_BENCHMARK_BY_REGION: dict[str, str] = {"US": "SPY", "UK": "ISF.L"}


# ----------------------------- request / result -----------------------------


class ThesisRunRequest(BaseModel):
    ticker: str
    focus_question: str | None = None
    thesis_id: UUID | None = None
    user_id: UUID | None = None


class StepError(BaseModel):
    step: str
    actor: str
    message: str


class ThesisRunResult(BaseModel):
    thesis_id: UUID
    status: str
    instrument: Instrument
    research_stance: str | None = None
    evidence_strength: float | None = None
    dossier: dict[str, Any] | None = None
    sources_persisted: int = 0
    chunks_persisted: int = 0
    citations_persisted: int = 0
    errors: list[StepError] = Field(default_factory=list)


# ----------------------------- dependencies -----------------------------


@dataclass
class Deps:
    """Orchestrator dependency table — every external call is mockable here."""

    # Connectors
    news_search: Callable[..., Awaitable[list[RawDocument]]] = news_api.search_everything
    fred_get_series: Callable[..., Awaitable[Any]] = fred.get_series_observations
    sec_get_filings: Callable[..., Awaitable[list[Any]]] = sec_edgar.get_recent_filings
    rns_search: Callable[..., Awaitable[list[RawDocument]]] = uk_rns.search_rns
    ons_get_timeseries: Callable[..., Awaitable[Any]] = ons.get_timeseries
    prices_get: Callable[..., Awaitable[PriceSeries]] = prices.get_history
    company_ir_fetch: Callable[..., Awaitable[RawDocument]] = company_ir.fetch_url

    # Ingest
    chunk_document: Callable[..., list[Chunk]] = chunker.chunk_document
    embed_documents: Callable[..., Awaitable[list[list[float]]]] = embedder.embed_documents
    insert_source: Callable[..., Awaitable[UUID]] = document_store.insert_source
    insert_chunks: Callable[..., Awaitable[list[UUID]]] = document_store.insert_chunks
    retriever_search: Callable[..., Awaitable[list[Retrieval]]] = retriever.search
    insert_citation: Callable[..., Awaitable[UUID]] = citations.insert_citation
    validate_citation: Callable[..., Any] = citations.validate_citation

    # Audit + DB row management
    audit_log: Callable[..., Awaitable[UUID | None]] = audit.log_event
    create_thesis_row: Callable[..., Awaitable[UUID]] = field(default=None)  # type: ignore[assignment]
    update_thesis_row: Callable[..., Awaitable[None]] = field(default=None)  # type: ignore[assignment]

    # Agents — LLM
    news_run: Callable[..., Awaitable[Any]] = news_agent.run
    disclosure_run: Callable[..., Awaitable[Any]] = disclosure_agent.run
    uk_rns_run: Callable[..., Awaitable[Any]] = uk_rns_agent.run
    earnings_reviewer_run: Callable[..., Awaitable[Any]] = earnings_reviewer_agent.run
    market_research_run: Callable[..., Awaitable[Any]] = market_research_agent.run
    macro_run: Callable[..., Awaitable[Any]] = macro_agent.run
    uk_macro_run: Callable[..., Awaitable[Any]] = uk_macro_agent.run
    valuation_run: Callable[..., Awaitable[Any]] = valuation_agent.run
    thesis_tracker_run: Callable[..., Awaitable[Any]] = thesis_tracker_agent.run
    synthesizer_run: Callable[..., Awaitable[Any]] = synthesizer.run

    # Agents — computational
    price_run: Callable[..., Awaitable[Any]] = price_agent.run
    quant_validation_run: Callable[..., Awaitable[Any]] = quant_validation_agent.run

    # Configuration
    fred_series: tuple[str, ...] = _DEFAULT_FRED_SERIES
    ons_series: tuple[tuple[str, str], ...] = _DEFAULT_ONS_SERIES
    news_window_days: int = _NEWS_WINDOW_DAYS
    price_window_days: int = _PRICE_WINDOW_DAYS
    sec_filing_limit: int = 5
    """Maximum number of SEC filings to fetch full text for. Filings can be
    several hundred KB each, so embedding cost scales fast."""

    def __post_init__(self) -> None:
        if self.create_thesis_row is None:
            self.create_thesis_row = _default_create_thesis_row
        if self.update_thesis_row is None:
            self.update_thesis_row = _default_update_thesis_row


# ----------------------------- DB helpers (default impls) -----------------------------


_INSERT_THESIS_SQL = """
    insert into theses (id, user_id, ticker, focus_question, status)
    values ($1, $2, $3, $4, 'running')
    on conflict (id) do update set status = 'running'
"""

_UPDATE_THESIS_SQL = """
    update theses
    set status = $2,
        research_stance = $3,
        evidence_strength = $4,
        summary = $5::jsonb,
        error = $6
    where id = $1
"""


async def _default_create_thesis_row(
    *,
    thesis_id: UUID,
    user_id: UUID | None,
    ticker: str,
    focus_question: str | None,
    conn: asyncpg.Connection | None = None,
) -> UUID:
    if conn is not None:
        await conn.execute(_INSERT_THESIS_SQL, thesis_id, user_id, ticker, focus_question)
        return thesis_id
    if get_pool() is None:
        log.warning("create_thesis_row: pool unavailable; thesis row not persisted")
        return thesis_id
    async with acquire() as c:
        await c.execute(_INSERT_THESIS_SQL, thesis_id, user_id, ticker, focus_question)
    return thesis_id


async def _default_update_thesis_row(
    *,
    thesis_id: UUID,
    status: str,
    research_stance: str | None = None,
    evidence_strength: float | None = None,
    summary: dict[str, Any] | None = None,
    error: str | None = None,
    conn: asyncpg.Connection | None = None,
) -> None:
    import json

    args = (
        thesis_id, status, research_stance, evidence_strength,
        json.dumps(summary or {}, default=str), error,
    )
    if conn is not None:
        await conn.execute(_UPDATE_THESIS_SQL, *args)
        return
    if get_pool() is None:
        log.warning("update_thesis_row: pool unavailable; thesis row not updated")
        return
    async with acquire() as c:
        await c.execute(_UPDATE_THESIS_SQL, *args)


# ----------------------------- the orchestrator -----------------------------


@dataclass
class _IngestionResult:
    sources_by_kind: dict[str, list[RawDocument]] = field(default_factory=dict)
    fred_data_points: dict[str, float | None] = field(default_factory=dict)
    ons_data_points: dict[str, float | None] = field(default_factory=dict)
    price_series: PriceSeries | None = None
    benchmark_series: PriceSeries | None = None


class ThesisOrchestrator:
    def __init__(self, deps: Deps | None = None):
        self.deps = deps or Deps()

    async def run(self, request: ThesisRunRequest) -> ThesisRunResult:
        run = _ThesisRun(request, self.deps)
        return await run.execute()


# ----------------------------- the run state machine -----------------------------


class _ThesisRun:
    def __init__(self, request: ThesisRunRequest, deps: Deps):
        self.request = request
        self.deps = deps
        self.errors: list[StepError] = []
        try:
            self.instrument = identifiers.resolve(request.ticker)
        except ValueError as exc:
            raise ValueError(f"Invalid ticker {request.ticker!r}: {exc}") from exc
        self.thesis_id: UUID = request.thesis_id or uuid4()
        # Accumulated chunk text seen in any agent's retrieval set. Used at
        # citation-persist time to run validate_citation against the actual
        # supporting text rather than just trusting the model's UUID list.
        self._retrieved_texts: dict[UUID, str] = {}

    # ---------- error tracking ----------

    def _record_error(self, step: str, actor: str, exc: BaseException) -> None:
        msg = f"{type(exc).__name__}: {exc}"
        self.errors.append(StepError(step=step, actor=actor, message=msg))
        log.warning("step=%s actor=%s failed: %s", step, actor, msg)

    async def _audit_unavailable(self, actor: str, action: str, exc: BaseException) -> None:
        await self.deps.audit_log(
            actor=actor, action=action, status="warn",
            thesis_id=self.thesis_id,
            payload={"reason": f"{type(exc).__name__}: {exc}"},
        )

    # ---------- main flow ----------

    async def execute(self) -> ThesisRunResult:
        await self.deps.audit_log(
            actor="orchestrator", action="run_started",
            thesis_id=self.thesis_id,
            payload={"ticker": self.instrument.ticker, "region": self.instrument.region},
        )

        try:
            await self.deps.create_thesis_row(
                thesis_id=self.thesis_id,
                user_id=self.request.user_id,
                ticker=self.instrument.ticker,
                focus_question=self.request.focus_question,
            )
        except Exception as exc:
            self._record_error("create_thesis_row", "orchestrator", exc)

        ingestion = await self._ingest_sources()
        sources_persisted, chunks_persisted, source_id_by_kind = (
            await self._persist_and_chunk(ingestion)
        )
        agent_outputs = await self._run_agents(ingestion, source_id_by_kind)

        try:
            dossier = await self.deps.synthesizer_run(
                self.instrument.ticker,
                agent_outputs=agent_outputs,
                focus_question=self.request.focus_question,
                thesis_id=self.thesis_id,
            )
        except Exception as exc:
            self._record_error("synthesize", "synthesizer", exc)
            dossier = None

        citations_persisted = await self._persist_citations(agent_outputs, dossier)

        status = "completed" if dossier is not None else "failed"
        research_stance = dossier.research_stance if dossier else None
        evidence_strength = dossier.evidence_strength if dossier else None
        summary = dossier.model_dump(mode="json") if dossier else None

        try:
            await self.deps.update_thesis_row(
                thesis_id=self.thesis_id,
                status=status,
                research_stance=research_stance,
                evidence_strength=evidence_strength,
                summary=summary,
                error="; ".join(e.message for e in self.errors) or None,
            )
        except Exception as exc:
            self._record_error("update_thesis_row", "orchestrator", exc)

        await self.deps.audit_log(
            actor="orchestrator", action="run_finished",
            thesis_id=self.thesis_id, status="ok" if status == "completed" else "warn",
            payload={
                "status": status,
                "errors_count": len(self.errors),
                "sources_persisted": sources_persisted,
                "chunks_persisted": chunks_persisted,
                "citations_persisted": citations_persisted,
            },
        )

        return ThesisRunResult(
            thesis_id=self.thesis_id,
            status=status,
            instrument=self.instrument,
            research_stance=research_stance,
            evidence_strength=evidence_strength,
            dossier=summary,
            sources_persisted=sources_persisted,
            chunks_persisted=chunks_persisted,
            citations_persisted=citations_persisted,
            errors=self.errors,
        )

    # ---------- ingestion ----------

    async def _ingest_sources(self) -> _IngestionResult:
        today = date.today()
        ingestion = _IngestionResult()

        async def safe_news() -> list[RawDocument]:
            try:
                from_d = today - timedelta(days=self.deps.news_window_days)
                stripped = identifiers.stripped_symbol(self.instrument.ticker)
                docs = await self.deps.news_search(
                    stripped, from_date=from_d, to_date=today, page_size=25,
                )
                return docs
            except (MissingApiKeyError, ConnectorError) as exc:
                self._record_error("ingest", "news_api", exc)
                await self._audit_unavailable("news_api", "fetch", exc)
                return []

        async def safe_sec() -> list[RawDocument]:
            if self.instrument.region != "US" or self.instrument.asset_class != "equity":
                return []
            try:
                filings = await self.deps.sec_get_filings(
                    self.instrument.ticker, limit=self.deps.sec_filing_limit,
                )
            except (MissingApiKeyError, ConnectorError) as exc:
                self._record_error("ingest", "sec_edgar", exc)
                await self._audit_unavailable("sec_edgar", "fetch_filings", exc)
                return []

            # Fetch each filing's primary document so the disclosure agent reads
            # the actual filing body, not just metadata. Failures per filing are
            # logged and skipped — we keep what we can fetch.
            docs: list[RawDocument] = []
            for f in filings:
                kind = f"sec_{f.form.lower().replace('-', '')}"
                title = f"{f.form} filed {f.filing_date.isoformat()}"
                meta = {
                    "cik": f.cik,
                    "accession_number": f.accession_number,
                    "form": f.form,
                    "filing_date": f.filing_date.isoformat(),
                }
                try:
                    body = await self.deps.company_ir_fetch(
                        f.primary_doc_url, title=title,
                    )
                except ConnectorError as exc:
                    self._record_error(
                        "ingest", f"sec_filing:{f.accession_number}", exc,
                    )
                    await self._audit_unavailable(
                        "sec_edgar", f"fetch_filing:{f.accession_number}", exc,
                    )
                    continue
                docs.append(
                    body.model_copy(update={
                        "kind": kind,
                        "title": title,
                        "metadata": {**body.metadata, **meta},
                    })
                )
            return docs

        async def safe_rns() -> list[RawDocument]:
            if self.instrument.region != "UK":
                return []
            try:
                from_d = today - timedelta(days=self.deps.news_window_days)
                return await self.deps.rns_search(
                    self.instrument.ticker, from_date=from_d, to_date=today, page_size=25,
                )
            except (MissingApiKeyError, ConnectorError) as exc:
                self._record_error("ingest", "uk_rns", exc)
                await self._audit_unavailable("uk_rns", "fetch", exc)
                return []

        async def safe_prices() -> tuple[PriceSeries | None, PriceSeries | None]:
            start_d = today - timedelta(days=self.deps.price_window_days)
            try:
                series = await self.deps.prices_get(
                    self.instrument.ticker, start_date=start_d, end_date=today,
                )
            except (MissingApiKeyError, ConnectorError) as exc:
                self._record_error("ingest", "prices", exc)
                await self._audit_unavailable("prices", "fetch", exc)
                series = None
            bench_ticker = _BENCHMARK_BY_REGION.get(self.instrument.region)
            bench: PriceSeries | None = None
            if bench_ticker:
                try:
                    bench = await self.deps.prices_get(
                        bench_ticker, start_date=start_d, end_date=today,
                    )
                except (MissingApiKeyError, ConnectorError) as exc:
                    self._record_error("ingest", "prices_benchmark", exc)
                    await self._audit_unavailable(
                        "prices", f"fetch_benchmark:{bench_ticker}", exc,
                    )
            return series, bench

        async def safe_fred() -> dict[str, float | None]:
            out: dict[str, float | None] = {}
            for series_id in self.deps.fred_series:
                try:
                    ts = await self.deps.fred_get_series(series_id)
                    last = next(
                        (p.value for p in reversed(ts.points) if p.value is not None),
                        None,
                    )
                    out[series_id] = last
                except (MissingApiKeyError, ConnectorError) as exc:
                    self._record_error("ingest", f"fred:{series_id}", exc)
                    await self._audit_unavailable("fred", f"fetch_series:{series_id}", exc)
                    out[series_id] = None
            return out

        async def safe_ons() -> dict[str, float | None]:
            if self.instrument.region != "UK":
                return {}
            out: dict[str, float | None] = {}
            for dataset, cdid in self.deps.ons_series:
                try:
                    ts = await self.deps.ons_get_timeseries(dataset, cdid)
                    last = next(
                        (p.value for p in reversed(ts.points) if p.value is not None),
                        None,
                    )
                    out[cdid] = last
                except (MissingApiKeyError, ConnectorError) as exc:
                    self._record_error("ingest", f"ons:{cdid}", exc)
                    await self._audit_unavailable(
                        "ons", f"fetch_series:{dataset}/{cdid}", exc,
                    )
                    out[cdid] = None
            return out

        # Fan out — every safe_* swallows its own errors so gather is safe.
        news_docs, sec_docs, rns_docs, (price_series, bench_series), fred_pts, ons_pts = (
            await asyncio.gather(
                safe_news(), safe_sec(), safe_rns(),
                safe_prices(), safe_fred(), safe_ons(),
            )
        )

        if news_docs:
            ingestion.sources_by_kind["news"] = news_docs
        if sec_docs:
            for doc in sec_docs:
                ingestion.sources_by_kind.setdefault(doc.kind, []).append(doc)
        if rns_docs:
            ingestion.sources_by_kind.setdefault("rns_proxy", []).extend(rns_docs)
        ingestion.fred_data_points = fred_pts
        ingestion.ons_data_points = ons_pts
        ingestion.price_series = price_series
        ingestion.benchmark_series = bench_series

        return ingestion

    # ---------- persistence + embedding ----------

    async def _persist_and_chunk(
        self, ingestion: _IngestionResult
    ) -> tuple[int, int, dict[str, list[UUID]]]:
        sources_persisted = 0
        chunks_persisted = 0
        source_id_by_kind: dict[str, list[UUID]] = {}

        # Pass 1: persist source rows + chunk every doc.
        all_chunks: list[Chunk] = []
        chunk_to_source: list[UUID] = []
        for kind, docs in ingestion.sources_by_kind.items():
            for doc in docs:
                try:
                    source_id = await self.deps.insert_source(self.thesis_id, doc)
                except Exception as exc:
                    self._record_error("persist_source", kind, exc)
                    continue
                source_id_by_kind.setdefault(kind, []).append(source_id)
                sources_persisted += 1
                for chunk in self.deps.chunk_document(doc):
                    all_chunks.append(chunk)
                    chunk_to_source.append(source_id)

        if not all_chunks:
            return sources_persisted, 0, source_id_by_kind

        # Pass 2: one embed call across all chunks (the embedder batches internally).
        try:
            embeddings = await self.deps.embed_documents([c.text for c in all_chunks])
        except (MissingApiKeyError, ConnectorError) as exc:
            self._record_error("embed", "voyage", exc)
            await self._audit_unavailable("voyage", "embed_documents", exc)
            return sources_persisted, 0, source_id_by_kind

        # Pass 3: insert chunks per source. Group to use one transaction per source.
        from collections import defaultdict

        grouped: dict[UUID, list[tuple[Chunk, list[float]]]] = defaultdict(list)
        for chunk, embedding, source_id in zip(
            all_chunks, embeddings, chunk_to_source, strict=True
        ):
            grouped[source_id].append((chunk, embedding))

        for source_id, items in grouped.items():
            try:
                ids = await self.deps.insert_chunks(
                    source_id,
                    [c for c, _ in items],
                    [e for _, e in items],
                )
            except Exception as exc:
                self._record_error("persist_chunks", str(source_id), exc)
                continue
            chunks_persisted += len(ids)

        return sources_persisted, chunks_persisted, source_id_by_kind

    # ---------- agent fan-out ----------

    async def _retrieve(
        self,
        *,
        query: str,
        source_kinds: list[str] | None,
        top_k: int = 12,
    ) -> list[Retrieval]:
        try:
            results = await self.deps.retriever_search(
                query, thesis_id=self.thesis_id,
                source_kinds=source_kinds, top_k=top_k,
            )
        except (MissingApiKeyError, ConnectorError) as exc:
            self._record_error("retrieve", "retriever", exc)
            return []
        except Exception as exc:
            self._record_error("retrieve", "retriever", exc)
            return []
        # Cache chunk text so _persist_citations can validate claims against
        # the actual supporting text without re-fetching.
        for r in results:
            self._retrieved_texts[r.chunk_id] = r.text
        return results

    async def _safe_agent(
        self,
        agent_name: str,
        runner: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any | None:
        try:
            return await runner(*args, **kwargs)
        except Exception as exc:
            self._record_error("agent", agent_name, exc)
            return None

    async def _run_agents(
        self,
        ingestion: _IngestionResult,
        source_id_by_kind: dict[str, list[UUID]],
    ) -> dict[str, Any]:
        ticker = self.instrument.ticker
        is_us_equity = (
            self.instrument.region == "US" and self.instrument.asset_class == "equity"
        )
        is_uk = self.instrument.region == "UK"

        # Per-agent retrievals.
        news_chunks_task = self._retrieve(
            query=f"{ticker} recent news developments",
            source_kinds=["news"],
        )
        market_chunks_task = self._retrieve(
            query=f"{ticker} sector competitive position peers",
            source_kinds=None,
        )
        macro_chunks_task = self._retrieve(
            query=f"{ticker} macro rates inflation",
            source_kinds=["news"],
        )
        valuation_chunks_task = self._retrieve(
            query=f"{ticker} valuation multiples peers leverage",
            source_kinds=None,
        )
        earnings_chunks_task = self._retrieve(
            query=f"{ticker} earnings results guidance",
            source_kinds=None,
        )

        disclosure_chunks_task: Awaitable[list[Retrieval]]
        if is_us_equity:
            disclosure_chunks_task = self._retrieve(
                query=f"{ticker} business operations risk factors",
                source_kinds=["sec_10k", "sec_10q", "sec_8k"],
            )
        elif is_uk:
            disclosure_chunks_task = self._retrieve(
                query=f"{ticker} annual report risk factors",
                source_kinds=["rns_proxy"],
            )
        else:
            disclosure_chunks_task = _empty_list()

        rns_chunks_task: Awaitable[list[Retrieval]]
        rns_chunks_task = (
            self._retrieve(query=f"{ticker} RNS announcements", source_kinds=["rns_proxy"])
            if is_uk else _empty_list()
        )
        uk_macro_chunks_task: Awaitable[list[Retrieval]]
        uk_macro_chunks_task = (
            self._retrieve(query=f"{ticker} UK macro Bank Rate sterling", source_kinds=None)
            if is_uk else _empty_list()
        )

        (
            news_chunks, disclosure_chunks, rns_chunks, market_chunks,
            macro_chunks, uk_macro_chunks, valuation_chunks, earnings_chunks,
        ) = await asyncio.gather(
            news_chunks_task, disclosure_chunks_task, rns_chunks_task, market_chunks_task,
            macro_chunks_task, uk_macro_chunks_task, valuation_chunks_task,
            earnings_chunks_task,
        )

        # Run section agents in parallel.
        section_tasks = {
            "news": self._safe_agent(
                "news_agent", self.deps.news_run, ticker,
                retrievals=news_chunks, thesis_id=self.thesis_id,
            ),
            "market_research": self._safe_agent(
                "market_research_agent", self.deps.market_research_run, ticker,
                retrievals=market_chunks, thesis_id=self.thesis_id,
            ),
            "macro": self._safe_agent(
                "macro_agent", self.deps.macro_run, ticker,
                retrievals=macro_chunks, data_points=ingestion.fred_data_points,
                thesis_id=self.thesis_id,
            ),
            "valuation": self._safe_agent(
                "valuation_agent", self.deps.valuation_run, ticker,
                retrievals=valuation_chunks, thesis_id=self.thesis_id,
            ),
            "earnings_reviewer": self._safe_agent(
                "earnings_reviewer_agent", self.deps.earnings_reviewer_run, ticker,
                retrievals=earnings_chunks, focus_question=self.request.focus_question,
                thesis_id=self.thesis_id,
            ),
        }
        if is_us_equity or is_uk:
            section_tasks["disclosure"] = self._safe_agent(
                "disclosure_agent", self.deps.disclosure_run, ticker,
                retrievals=disclosure_chunks, thesis_id=self.thesis_id,
            )
        if is_uk:
            section_tasks["uk_rns"] = self._safe_agent(
                "uk_rns_agent", self.deps.uk_rns_run, ticker,
                retrievals=rns_chunks, thesis_id=self.thesis_id,
            )
            section_tasks["uk_macro"] = self._safe_agent(
                "uk_macro_agent", self.deps.uk_macro_run, ticker,
                retrievals=uk_macro_chunks, data_points=ingestion.ons_data_points,
                thesis_id=self.thesis_id,
            )

        section_keys = list(section_tasks.keys())
        section_results = await asyncio.gather(*section_tasks.values())
        outputs: dict[str, Any] = {
            k: v for k, v in zip(section_keys, section_results) if v is not None
        }

        # Computational agents (no LLM) — run regardless of section availability.
        if ingestion.price_series is not None:
            price_out = await self._safe_agent(
                "price_agent", self.deps.price_run,
                ingestion.price_series, benchmark=ingestion.benchmark_series,
            )
            quant_out = await self._safe_agent(
                "quant_validation_agent", self.deps.quant_validation_run,
                ingestion.price_series, benchmark=ingestion.benchmark_series,
            )
            if price_out is not None:
                outputs["price"] = price_out
            if quant_out is not None:
                outputs["quant_validation"] = quant_out

        # Thesis tracker — runs after section agents and consumes their summaries.
        thesis_summaries = {k: v.model_dump(mode="json") for k, v in outputs.items()}
        thesis_chunks = await self._retrieve(
            query=f"{ticker} thesis investment case", source_kinds=None, top_k=20,
        )
        tracker_out = await self._safe_agent(
            "thesis_tracker_agent", self.deps.thesis_tracker_run, ticker,
            retrievals=thesis_chunks, agent_summaries=thesis_summaries,
            focus_question=self.request.focus_question, thesis_id=self.thesis_id,
        )
        if tracker_out is not None:
            outputs["thesis_tracker"] = tracker_out

        return outputs

    # ---------- citations ----------

    async def _persist_citations(
        self, agent_outputs: dict[str, Any], dossier: Any | None,
    ) -> int:
        """Persist one citations row per (section, claim, chunk_ids) triple.

        Each row is scored via `citations.validate_citation` against the text
        of its cited chunks (cached during retrieval). The overlap_score is
        stored as `confidence`. Rows with no extractable supporting text fall
        back to confidence=None so the audit trail can distinguish "validated
        but weak" from "couldn't validate at all".
        """
        count = 0

        async def store(section: str, claim: str, chunk_ids: Sequence[UUID]) -> None:
            nonlocal count
            if not claim or not chunk_ids:
                return
            supporting_texts = [
                t for cid in chunk_ids
                if (t := self._retrieved_texts.get(cid))
            ]
            confidence: float | None
            if supporting_texts:
                validation = self.deps.validate_citation(claim, supporting_texts)
                confidence = float(validation.overlap_score)
                if not validation.ok:
                    await self.deps.audit_log(
                        actor="orchestrator", action="citation_low_overlap",
                        status="warn", thesis_id=self.thesis_id,
                        payload={
                            "section": section,
                            "claim": claim[:200],
                            "overlap_score": confidence,
                            "reason": validation.reason,
                        },
                    )
            else:
                confidence = None
            try:
                await self.deps.insert_citation(
                    self.thesis_id, section, claim, list(chunk_ids),
                    confidence=confidence,
                )
                count += 1
            except Exception as exc:
                self._record_error("persist_citation", section, exc)

        for section, output in agent_outputs.items():
            if not isinstance(output, BaseModel):
                continue
            await self._walk_for_citations(output, section, store)

        if dossier is not None and isinstance(dossier, BaseModel):
            await self._walk_for_citations(dossier, "dossier", store)

        return count

    @staticmethod
    def _citation_topic(citation_field_name: str) -> str:
        """Strip the trailing `_cited_chunk_ids` to get the topic word(s).

        e.g. 'headline_cited_chunk_ids' -> 'headline'
             'summary_cited_chunk_ids'  -> 'summary'
             'cited_chunk_ids'          -> '' (generic)
        """
        suffix = "_cited_chunk_ids"
        if citation_field_name.endswith(suffix) and citation_field_name != "cited_chunk_ids":
            return citation_field_name[: -len(suffix)]
        return ""

    @staticmethod
    def _find_citations_for_text(
        text_name: str, citation_fields: dict[str, Sequence[UUID]]
    ) -> Sequence[UUID]:
        """Resolve which citation list supports a given text field.

        Pairing precedence:
          1. Exact suffix:  `<text>_cited_chunk_ids`  (e.g. business_summary)
          2. Word-level:    citation field whose topic appears as a word in the
                            text field name (valuation_summary <- summary_cited_chunk_ids,
                            headline_read <- headline_cited_chunk_ids,
                            thesis_statement <- statement_cited_chunk_ids)
          3. Generic fallback: `cited_chunk_ids` if present.
        """
        # 1. Exact
        exact_key = f"{text_name}_cited_chunk_ids"
        if citation_fields.get(exact_key):
            return citation_fields[exact_key]
        # 2. Word-level
        text_parts = set(text_name.split("_"))
        for cf_name, cf_value in citation_fields.items():
            if not cf_value:
                continue
            topic = _ThesisRun._citation_topic(cf_name)
            if topic and topic in text_parts:
                return cf_value
        # 3. Generic
        if citation_fields.get("cited_chunk_ids"):
            return citation_fields["cited_chunk_ids"]
        if citation_fields.get("citation_ids"):
            return citation_fields["citation_ids"]
        return []

    @staticmethod
    def _is_literal_field(model_class: type[BaseModel], field_name: str) -> bool:
        """True if the field's type annotation is `Literal[...]`. We skip these
        when collecting "claim" text — values like 'up'/'down'/'positive' are
        enum-style labels, not analyst claims."""
        import typing

        info = model_class.model_fields.get(field_name)
        if info is None:
            return False
        return typing.get_origin(info.annotation) is typing.Literal

    @staticmethod
    async def _walk_for_citations(
        node: Any,
        section: str,
        store: Callable[[str, str, Sequence[UUID]], Awaitable[None]],
    ) -> None:
        """Walk a Pydantic tree and call `store(section, claim, chunk_ids)` for
        every (text-bearing field, paired citation field) combination on each model."""
        if isinstance(node, BaseModel):
            from .agents._base import _is_citation_field

            model_cls = type(node)
            citation_fields: dict[str, Sequence[UUID]] = {}
            text_fields: dict[str, str] = {}
            for fname in model_cls.model_fields:
                fval = getattr(node, fname)
                if _is_citation_field(fname) and isinstance(fval, list):
                    citation_fields[fname] = fval
                elif (
                    isinstance(fval, str)
                    and fval
                    and fname not in {"notes", "analyst_disclaimer"}
                    and not _ThesisRun._is_literal_field(model_cls, fname)
                ):
                    text_fields[fname] = fval

            for text_name, text_val in text_fields.items():
                ids = _ThesisRun._find_citations_for_text(text_name, citation_fields)
                if ids:
                    await store(section, text_val, ids)

            # Recurse into nested models / lists / dicts.
            for fname in model_cls.model_fields:
                fval = getattr(node, fname)
                if isinstance(fval, (BaseModel, list, dict)):
                    await _ThesisRun._walk_for_citations(fval, section, store)

        elif isinstance(node, list):
            for item in node:
                await _ThesisRun._walk_for_citations(item, section, store)
        elif isinstance(node, dict):
            for v in node.values():
                await _ThesisRun._walk_for_citations(v, section, store)


# ----------------------------- helpers -----------------------------


async def _empty_list() -> list[Retrieval]:
    return []
