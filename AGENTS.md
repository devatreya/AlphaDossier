# AGENTS.md — AI-quant

Guidance for Codex when working in this repo.

## What this project is

UK/US public-market research copilot. Takes a ticker, produces a cited research dossier (executive summary, bull/bear, catalysts, risks, disconfirming evidence, news, macro, disclosure/RNS evidence, basic price/risk sanity check).

Framing: **analyst-in-the-loop research copilot**. Not an AI hedge fund, trading bot, or advisor.

## Build phases

Work proceeds phase by phase. Do not jump ahead.

1. Repo scaffold — Next.js + FastAPI + Supabase + DB migration + health endpoint
2. Source connectors — SEC EDGAR, RNS, FCA NSM, IR, News API, FRED, ONS, prices
3. Document store, chunker, embedder, retriever, citations
4. Codex research agents + orchestrator + synthesizer
5. Thesis viewer, citation popover, audit page
6. Demo seed + smoke tests

## API key rules

User already has `NEWS_API_KEY` and `FRED_API_KEY`.

Required for MVP: `ANTHROPIC_API_KEY`, `NEWS_API_KEY`, `FRED_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`.

Recommended: `VOYAGE_API_KEY` for embeddings.

Optional: `OPENAI_API_KEY` (fallback embeddings only), `FMP_API_KEY` (transcripts later), `COMPANIES_HOUSE_API_KEY` (UK enrichment).

Do **not** require OpenAI, FMP, Tavily, or paid SEC APIs for the MVP. Prefer free/public sources: SEC EDGAR, FCA NSM, RNS, company IR pages, ONS, yfinance/Stooq.

If a key is missing: do not crash. Mark the relevant agent output as unavailable, continue the thesis with available sources, and log the missing-key issue in `audit_log`.

## Output rules

- No fake citations. Every important claim cites a chunk.
- Every number cites a source or is marked `[UNSOURCED]`.
- No buy/sell recommendation; no "trade now" language.
- Always include limitations and an analyst-review disclaimer.

## Conventions

- Backend: FastAPI, Pydantic v2, async SQLAlchemy or asyncpg, Python 3.11+.
- Frontend: Next.js App Router, TypeScript strict, Tailwind, Supabase JS client.
- Embeddings via Voyage (`voyage-finance-2`); store vectors in Supabase pgvector.
- All agents return Pydantic-validated JSON; orchestrator persists raw + parsed output to `audit_log`.
