from __future__ import annotations

import httpx
import pytest

from services.api.data import _http
from services.api.data._errors import ConnectorError

from .conftest import make_mock_client


async def test_retries_on_429_then_succeeds() -> None:
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"e": "slow"})
        return httpx.Response(200, json={"ok": True})

    async with make_mock_client(handler) as client:
        result = await _http.request_json(
            client, "GET", "https://x/", retries=2, backoff=0, provider="test",
        )

    assert result == {"ok": True}
    assert counter["n"] == 2


async def test_retries_exhausted_on_persistent_429() -> None:
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"e": "slow"})

    async with make_mock_client(handler) as client:
        with pytest.raises(ConnectorError, match="429"):
            await _http.request_json(
                client, "GET", "https://x/", retries=2, backoff=0, provider="test",
            )
    # initial + 2 retries = 3 total attempts
    assert counter["n"] == 3


async def test_retry_after_caps_long_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bogus Retry-After: 99999 must not actually sleep that long — we cap it."""
    seen_delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        seen_delays.append(delay)

    monkeypatch.setattr(_http.asyncio, "sleep", fake_sleep)
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "99999"}, json={})
        return httpx.Response(200, json={"ok": True})

    async with make_mock_client(handler) as client:
        result = await _http.request_json(
            client, "GET", "https://x/", retries=2, backoff=0, provider="test",
        )
    assert result == {"ok": True}
    assert seen_delays == [_http.MAX_RETRY_AFTER]


async def test_4xx_other_than_429_does_not_retry() -> None:
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(404, text="missing")

    async with make_mock_client(handler) as client:
        with pytest.raises(ConnectorError, match="404"):
            await _http.request_json(
                client, "GET", "https://x/", retries=3, backoff=0, provider="test",
            )
    assert counter["n"] == 1


async def test_5xx_still_retries() -> None:
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    async with make_mock_client(handler) as client:
        result = await _http.request_json(
            client, "GET", "https://x/", retries=3, backoff=0, provider="test",
        )
    assert result == {"ok": True}
    assert counter["n"] == 3
