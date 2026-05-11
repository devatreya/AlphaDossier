from __future__ import annotations

import json
from uuid import uuid4

import pytest

from services.api import audit, db

from ..ingest.conftest import FakeConn, find_call


async def test_log_event_writes_row() -> None:
    conn = FakeConn()
    new_id = uuid4()
    conn.fetchval_results = [new_id]
    thesis_id = uuid4()

    out = await audit.log_event(
        actor="news_agent",
        action="agent_call",
        thesis_id=thesis_id,
        status="ok",
        model="claude-sonnet-4-6",
        input_tokens=100, output_tokens=50,
        cost_usd=0.01, latency_ms=420,
        payload={"output": {"k": "v"}},
        conn=conn,
    )
    assert out == new_id
    sql, args = find_call(conn, method="fetchval", contains="insert into audit_log")
    assert args[0] == thesis_id
    assert args[2] == "news_agent"
    assert args[3] == "agent_call"
    assert args[4] == "ok"
    assert args[5] == "claude-sonnet-4-6"
    # payload arg is the JSON-encoded string.
    assert json.loads(args[10]) == {"output": {"k": "v"}}


async def test_log_event_invalid_status_raises() -> None:
    conn = FakeConn()
    with pytest.raises(ValueError, match="invalid audit status"):
        await audit.log_event(
            actor="x", action="y", status="weird", conn=conn,
        )


async def test_log_event_safe_when_pool_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """When DATABASE_URL is unset, log_event must not raise — the orchestrator
    keeps going and the analyst loses the audit row but not the thesis."""
    monkeypatch.setattr(db, "_pool", None)
    out = await audit.log_event(actor="news_agent", action="agent_call")
    assert out is None


async def test_log_event_serialises_non_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Payloads containing non-JSON-serialisable values must round-trip via repr."""
    conn = FakeConn()
    conn.fetchval_results = [uuid4()]

    class _Foo:
        def __repr__(self) -> str:
            return "<Foo>"

    await audit.log_event(
        actor="x", action="y",
        payload={"x": _Foo()},
        conn=conn,
    )
    sql, args = find_call(conn, method="fetchval", contains="insert into audit_log")
    assert "<Foo>" in args[10]
