"""Append-only audit log writer.

Every connector call, agent run, and synthesizer invocation is expected to log
one row here. Phase 5's /audit page reads from `audit_log` directly. The schema
is at db/migrations/001_init.sql.

Failure mode: audit logging itself must never break the caller. If the DB is
unreachable we log a warning and return None. The thesis run continues.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from .db import acquire, get_pool

log = logging.getLogger(__name__)

_INSERT_SQL = """
    insert into audit_log
        (thesis_id, job_id, actor, action, status, model,
         input_tokens, output_tokens, cost_usd, latency_ms, payload)
    values
        ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
    returning id
"""


def _safe_json(value: dict[str, Any] | None) -> str:
    """Serialise to JSON, falling back to repr for non-serialisable values."""
    return json.dumps(value or {}, default=repr)


async def log_event(
    actor: str,
    action: str,
    *,
    thesis_id: UUID | None = None,
    job_id: UUID | None = None,
    status: str = "ok",
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    latency_ms: int | None = None,
    payload: dict[str, Any] | None = None,
    conn: asyncpg.Connection | None = None,
) -> UUID | None:
    """Insert one audit row. Returns the row id, or None if the DB is unavailable.

    Audit logging must not crash callers — DB errors are downgraded to warnings.
    """
    if status not in {"ok", "warn", "error"}:
        raise ValueError(f"invalid audit status {status!r}")

    args = (
        thesis_id, job_id, actor, action, status, model,
        input_tokens, output_tokens, cost_usd, latency_ms,
        _safe_json(payload),
    )

    try:
        if conn is not None:
            return await conn.fetchval(_INSERT_SQL, *args)
        if get_pool() is None:
            log.warning(
                "audit: pool unavailable; dropping event actor=%s action=%s",
                actor, action,
            )
            return None
        async with acquire() as c:
            return await c.fetchval(_INSERT_SQL, *args)
    except Exception:
        log.exception("audit: failed to write event actor=%s action=%s", actor, action)
        return None
