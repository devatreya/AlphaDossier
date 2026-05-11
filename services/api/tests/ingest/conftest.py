"""Lightweight fake asyncpg.Connection for unit-testing DB modules.

Records the SQL + args of every call so tests can assert on the query shape
without bringing up a real Postgres. Returns user-supplied canned results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from contextlib import asynccontextmanager


@dataclass
class FakeRecord(dict):
    """Mimics asyncpg.Record by being dict-like with attribute access on keys."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e


@dataclass
class FakeConn:
    fetchval_results: list[Any] = field(default_factory=list)
    fetchrow_results: list[Any] = field(default_factory=list)
    fetch_results: list[list[Any]] = field(default_factory=list)
    execute_results: list[Any] = field(default_factory=list)

    calls: list[tuple[str, str, tuple[Any, ...]]] = field(default_factory=list)
    """Each entry is (method_name, sql, args)."""

    @asynccontextmanager
    async def transaction(self):
        self.calls.append(("transaction_enter", "", ()))
        try:
            yield
            self.calls.append(("transaction_commit", "", ()))
        except Exception:
            self.calls.append(("transaction_rollback", "", ()))
            raise

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self.calls.append(("fetchval", sql, args))
        if not self.fetchval_results:
            return None
        return self.fetchval_results.pop(0)

    async def fetchrow(self, sql: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", sql, args))
        if not self.fetchrow_results:
            return None
        return self.fetchrow_results.pop(0)

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", sql, args))
        if not self.fetch_results:
            return []
        return self.fetch_results.pop(0)

    async def execute(self, sql: str, *args: Any) -> Any:
        self.calls.append(("execute", sql, args))
        if not self.execute_results:
            return None
        return self.execute_results.pop(0)


def find_call(conn: FakeConn, *, method: str, contains: str) -> tuple[str, tuple[Any, ...]]:
    """Helper: assert at least one call matched, return (sql, args) of the first."""
    for m, sql, args in conn.calls:
        if m == method and contains in sql:
            return sql, args
    raise AssertionError(
        f"No {method!r} call containing {contains!r}; saw {[(m, s[:40]) for m, s, _ in conn.calls]}"
    )


def make_fake_recorder(record: Callable[..., None]) -> FakeConn:
    return FakeConn()
