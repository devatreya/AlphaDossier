-- AI-quant initial schema
-- Run in Supabase SQL editor (or psql against DATABASE_URL).

create extension if not exists "pgcrypto";
create extension if not exists "vector";

-- Voyage voyage-finance-2 returns 1024-dim embeddings.
-- If switching providers, update the column type and reindex.

-- Tickers / instruments resolved by identifiers.py.
create table if not exists instruments (
    id              uuid primary key default gen_random_uuid(),
    ticker          text not null,
    region          text not null check (region in ('US', 'UK', 'OTHER')),
    name            text,
    asset_class     text,
    metadata        jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now(),
    unique (ticker, region)
);

-- A research run for a given ticker and (optional) focus question.
create table if not exists theses (
    id                  uuid primary key default gen_random_uuid(),
    user_id             uuid,
    instrument_id       uuid references instruments(id) on delete set null,
    ticker              text not null,
    focus_question      text,
    status              text not null default 'pending'
                        check (status in ('pending', 'running', 'completed', 'failed', 'cancelled')),
    research_stance     text check (research_stance in ('positive', 'neutral', 'negative')),
    evidence_strength   numeric,
    summary             jsonb,
    error               text,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);
create index if not exists theses_ticker_idx on theses (ticker);
create index if not exists theses_user_idx on theses (user_id);

-- A fetched source document (filing, RNS item, news article, IR PDF, macro series snapshot).
create table if not exists sources (
    id              uuid primary key default gen_random_uuid(),
    thesis_id       uuid references theses(id) on delete cascade,
    kind            text not null,        -- sec_10k, sec_10q, sec_8k, rns, fca_nsm, ir_pdf, news, fred, ons, price, etc.
    provider        text not null,        -- sec_edgar, lse_rns, fca, news_api, fred, ons, yfinance, ...
    url             text,
    title           text,
    published_at    timestamptz,
    fetched_at      timestamptz not null default now(),
    raw_path        text,                 -- optional pointer to stored raw bytes
    content_hash    text,
    metadata        jsonb not null default '{}'::jsonb
);
create index if not exists sources_thesis_idx on sources (thesis_id);
create index if not exists sources_kind_idx on sources (kind);

-- Chunked source text + embeddings.
create table if not exists chunks (
    id              uuid primary key default gen_random_uuid(),
    source_id       uuid not null references sources(id) on delete cascade,
    chunk_index     int not null,
    text            text not null,
    embedding       vector(1024),
    token_count     int,
    metadata        jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now(),
    unique (source_id, chunk_index)
);
create index if not exists chunks_source_idx on chunks (source_id);
-- ANN index for retrieval. Cosine works well for normalized embeddings.
create index if not exists chunks_embedding_ivfflat
    on chunks using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- Citation = a claim in the final thesis backed by one or more chunks.
create table if not exists citations (
    id              uuid primary key default gen_random_uuid(),
    thesis_id       uuid not null references theses(id) on delete cascade,
    section         text not null,        -- e.g. "bull_case", "catalysts", "macro"
    claim           text not null,
    chunk_ids       uuid[] not null default '{}',
    confidence      numeric,
    created_at      timestamptz not null default now()
);
create index if not exists citations_thesis_idx on citations (thesis_id);

-- Background job tracking for orchestrator runs.
create table if not exists jobs (
    id              uuid primary key default gen_random_uuid(),
    thesis_id       uuid references theses(id) on delete cascade,
    kind            text not null,        -- e.g. "build_thesis", "ingest_sources"
    status          text not null default 'queued'
                    check (status in ('queued', 'running', 'completed', 'failed', 'cancelled')),
    started_at      timestamptz,
    finished_at     timestamptz,
    error           text,
    metadata        jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now()
);
create index if not exists jobs_thesis_idx on jobs (thesis_id);
create index if not exists jobs_status_idx on jobs (status);

-- Append-only audit trail: every source fetch, agent call, model response.
create table if not exists audit_log (
    id              uuid primary key default gen_random_uuid(),
    thesis_id       uuid references theses(id) on delete cascade,
    job_id          uuid references jobs(id) on delete set null,
    actor           text not null,        -- agent name, connector name, "system"
    action          text not null,        -- "fetch_source", "agent_call", "embed", "synthesize", ...
    status          text not null default 'ok'
                    check (status in ('ok', 'warn', 'error')),
    model           text,
    input_tokens    int,
    output_tokens   int,
    cost_usd        numeric,
    latency_ms      int,
    payload         jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now()
);
create index if not exists audit_thesis_idx on audit_log (thesis_id);
create index if not exists audit_actor_idx on audit_log (actor);
create index if not exists audit_created_idx on audit_log (created_at desc);

-- Updated-at trigger for theses.
create or replace function set_updated_at() returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists theses_set_updated_at on theses;
create trigger theses_set_updated_at
    before update on theses
    for each row execute function set_updated_at();
