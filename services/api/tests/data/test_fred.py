from __future__ import annotations

from datetime import date

import httpx
import pytest

from services.api.data import fred
from services.api.data._errors import MissingApiKeyError

from .conftest import make_mock_client


def _obs_payload() -> dict:
    return {
        "observations": [
            {"date": "2026-01-01", "value": "5.5"},
            {"date": "2026-02-01", "value": "."},
            {"date": "2026-03-01", "value": "5.4"},
        ]
    }


def _info_payload() -> dict:
    return {
        "seriess": [
            {
                "title": "10-Year Treasury Constant Maturity Rate",
                "units": "Percent",
                "frequency": "Daily",
                "seasonal_adjustment_short": "NSA",
                "last_updated": "2026-04-01 09:00:00-05",
            }
        ]
    }


async def test_get_series_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        if "/series/observations" in request.url.path:
            assert "series_id=DGS10" in str(request.url)
            assert "api_key=k" in str(request.url)
            return httpx.Response(200, json=_obs_payload())
        if request.url.path.endswith("/series"):
            return httpx.Response(200, json=_info_payload())
        return httpx.Response(404)

    async with make_mock_client(handler) as client:
        ts = await fred.get_series_observations(
            "DGS10",
            observation_start=date(2026, 1, 1),
            observation_end=date(2026, 3, 31),
            client=client,
        )

    assert ts.series_id == "DGS10"
    assert ts.name == "10-Year Treasury Constant Maturity Rate"
    assert ts.frequency == "Daily"
    assert ts.units == "Percent"
    assert [p.value for p in ts.points] == [5.5, None, 5.4]
    assert [p.date for p in ts.points] == [
        date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1),
    ]


async def test_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError):
        await fred.get_series_observations("DGS10")
