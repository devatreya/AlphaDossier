# AlphaDossier

Analyst-in-the-loop AI research copilot for UK and US public-market investors.

Given a ticker, AlphaDossier produces a cited research dossier (executive summary, bull/bear, catalysts, risks, disconfirming evidence, recent news, macro context, disclosure/RNS evidence, basic price/risk sanity check). Every claim is grounded in a retrievable source chunk; numbers without sources are marked `[UNSOURCED]`.

This is a research tool, not investment advice.

## Stack

- **Frontend**: Next.js (App Router) + Supabase auth
- **Backend**: FastAPI (Python 3.11+)
- **Database**: Supabase Postgres + pgvector
- **LLM**: Anthropic Claude
- **Embeddings**: Voyage AI (`voyage-finance-2`)
- **Data sources**: SEC EDGAR, FCA NSM, RNS, Companies House, News API, FRED, ONS, Bank of England, yfinance / Stooq

## Repo layout

```
apps/web         Next.js frontend
services/api     FastAPI backend (importable as services.api.*)
db/migrations    SQL migrations (pgvector enabled)
prompts          Agent prompt templates
scripts          Demo seeding, smoke tests
pyproject.toml   Backend Python project (root)
```

## Getting started

### 1. Configure environment (two files)

```bash
cp .env.example .env                        # backend (root)
cp apps/web/.env.local.example apps/web/.env.local   # frontend
```

The two files are split because Next.js requires `NEXT_PUBLIC_` prefixes on any variable readable from client-side code. The frontend file mirrors a few values from the backend file — the comments in each `*.example` spell out which pairs:

| Backend (`.env`)             | Frontend (`apps/web/.env.local`) |
| ---------------------------- | -------------------------------- |
| `SUPABASE_URL`               | `NEXT_PUBLIC_SUPABASE_URL`       |
| `SUPABASE_ANON_KEY`          | `NEXT_PUBLIC_SUPABASE_ANON_KEY`  |
| `API_BASE_URL`               | `NEXT_PUBLIC_API_BASE_URL`       |

`SUPABASE_SERVICE_ROLE_KEY` and `DATABASE_URL` stay backend-only.

To boot the stack you need at minimum: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`. To actually run the orchestrator end-to-end you'll also need `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `NEWS_API_KEY`, and `FRED_API_KEY`; missing keys degrade gracefully (the orchestrator marks the relevant agent or connector unavailable, audits it, and proceeds).

### 2. Apply the database migration

In the Supabase SQL editor, paste `db/migrations/001_init.sql` and run it. This enables `pgvector` and creates the core tables.

### 3. Run the backend

Python **3.11 or newer** is required. Create the venv with an explicit interpreter so you don't accidentally pick up `python` 3.10 or older:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -V                       # should print 3.11.x or newer
pip install -e ".[dev]"
uvicorn services.api.main:app --reload --port 8000
```

Run from the repo root, not from inside `services/api/` — the backend is now a real package (`services.api.*`).

Probes:

```bash
curl http://localhost:8000/healthz    # liveness only — 200 if process is up
curl -i http://localhost:8000/readyz  # readiness — 200 ok / 503 degraded
```

`/readyz` returns 503 when the DB is not reachable. `/healthz` is a pure liveness probe and never fails as long as the process is running.

### 4. Run the frontend

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:3000. The home page server-renders `/readyz` so you can immediately see what's wired up.

## Verification

From repo root, with `.venv` active:

```bash
pytest                                    # backend tests
ruff check .                              # backend lint
mypy .                                    # backend type-check
( cd apps/web && npm run typecheck )      # frontend types
( cd apps/web && npm run build )          # frontend build
( cd apps/web && npm run lint )           # frontend lint (non-interactive)
( cd apps/web && npm test )               # component tests (vitest)
```

`npm run lint` is non-interactive — `apps/web/.eslintrc.json` is checked in so Next's setup prompt never fires.

Current state: **185 backend tests + 18 component tests** passing, ruff and mypy clean across the backend, frontend typecheck/lint/build clean.

## Build phases

- **Phase 1** ✅ scaffold — Next.js + FastAPI + Supabase + DB migration + split health/readiness
- **Phase 2** ✅ source connectors — SEC EDGAR, FCA NSM (stub), LSE RNS (proxy via News API), company IR, News API, FRED, ONS, prices (Yahoo + Stooq fallback)
- **Phase 3** ✅ ingest — pgvector schema, chunker (HTML/PDF/text), Voyage embedder, retriever, citation persistence with heuristic validator
- **Phase 4** ✅ agents — eleven LLM agents (news, disclosure, uk_rns, earnings_reviewer, market_research, macro, uk_macro, valuation, thesis_tracker, synthesizer) + two computational agents (price, quant_validation) + orchestrator with parallel ingestion, region-aware fan-out, and `validate_citation` runs before persist
- **Phase 5** ✅ web — thesis HTTP API, thesis viewer with abort-controller-guarded polling, citation popover, per-thesis audit page, demo route with a prebuilt NVDA dossier, vitest component tests
- **Phase 6** — not started: Python smoke-test scripts (`scripts/seed_demo.py`, `scripts/smoke_test.py`), cookie-aware Supabase SSR client for auth, additional demo dossiers (UK example)

## Disclaimer

AlphaDossier is a research prototype. Output may be incomplete or wrong. Do not act on it without independent analyst review.
