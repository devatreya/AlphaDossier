"""Shared test helpers for data connector tests."""
from __future__ import annotations

from typing import Callable

import httpx
import pytest

from services.api import config


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Each test starts with a fresh Settings instance so monkeypatched env vars
    are picked up without leaking across tests."""
    config.get_settings.cache_clear()


def make_mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
