# AI-quant

Analyst-in-the-loop AI research copilot for UK and US public-market investors.

Given a ticker, AI-quant produces a cited research dossier (executive summary, bull/bear, catalysts, risks, disconfirming evidence, recent news, macro context, disclosure/RNS evidence, basic price/risk sanity check). Every claim is grounded in a retrievable source chunk; numbers without sources are marked `[UNSOURCED]`.

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

## Phase 1: getting started

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

To run Phase 1 (health endpoint + frontend boot) you need at minimum: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.

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
```

`npm run lint` is non-interactive — `apps/web/.eslintrc.json` is checked in so Next's setup prompt never fires.

## Build phases

- **Phase 1** — scaffold (current): Next.js + FastAPI + Supabase + DB migration + split health/readiness
- **Phase 2** — source connectors (SEC, RNS, FCA NSM, IR, News API, FRED, ONS, prices)
- **Phase 3** — document store, chunker, embedder, retriever, citations
- **Phase 4** — Claude research agents + orchestrator + synthesizer
- **Phase 5** — thesis viewer, citation popover, audit page (and a cookie-aware Supabase server client)
- **Phase 6** — demo seed + smoke tests

## Disclaimer

AI-quant is a research prototype. Output may be incomplete or wrong. Do not act on it without independent analyst review.
