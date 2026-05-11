"""Async Postgres pool. Lazy: only initialised if DATABASE_URL is set."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from pgvector.asyncpg import register_vector

from .config import get_settings

log = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


def _normalise_dsn(url: str) -> str:
    # asyncpg expects postgres://, not postgresql+asyncpg://
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def _init_conn(conn: asyncpg.Connection) -> None:
    """Per-connection setup. Registers the pgvector codec so `embedding`
    columns can be read/written as Python lists/numpy arrays.

    Tolerant of a missing extension: logs a warning and continues so that
    non-vector queries still work and the failure surfaces at the actual
    vector op rather than at pool startup.
    """
    try:
        await register_vector(conn)
    except Exception:
        log.warning(
            "pgvector codec registration failed; vector ops will fail until "
            "the extension is installed",
            exc_info=True,
        )


async def init_pool() -> asyncpg.Pool | None:
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings()
    if not settings.database_url:
        log.warning("DATABASE_URL not set; running without DB pool.")
        return None

    _pool = await asyncpg.create_pool(
        dsn=_normalise_dsn(settings.database_url),
        min_size=1,
        max_size=10,
        command_timeout=30,
        init=_init_conn,
    )
    log.info("Postgres pool initialised.")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool | None:
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """Async context manager that yields a pooled connection.

    Raises RuntimeError if the pool has not been initialised (DATABASE_URL unset
    or init_pool not yet called).
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialised. Set DATABASE_URL.")
    async with pool.acquire() as conn:
        yield conn


async def ping() -> bool:
    """Run `select 1`. Returns True on success, False if no pool or query fails."""
    pool = get_pool()
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("select 1")
        return True
    except Exception:  # pragma: no cover
        log.exception("DB ping failed")
        return False
