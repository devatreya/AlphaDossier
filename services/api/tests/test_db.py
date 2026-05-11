from __future__ import annotations

import pytest

from services.api import db


async def test_acquire_raises_when_pool_uninitialised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an initialised pool, acquire() must raise — and do so as a real
    async context manager (i.e. the error surfaces on `async with`, not on call)."""
    monkeypatch.setattr(db, "_pool", None)
    cm = db.acquire()  # constructing the cm must not raise
    with pytest.raises(RuntimeError, match="DB pool is not initialised"):
        async with cm:
            pass


async def test_ping_false_without_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "_pool", None)
    assert await db.ping() is False


def test_normalise_dsn() -> None:
    assert (
        db._normalise_dsn("postgresql+asyncpg://u:p@h/db")
        == "postgresql://u:p@h/db"
    )
    assert db._normalise_dsn("postgres://u:p@h/db") == "postgres://u:p@h/db"
