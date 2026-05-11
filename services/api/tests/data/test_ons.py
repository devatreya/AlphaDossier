from __future__ import annotations

from datetime import date

import httpx

from services.api.data import ons

from .conftest import make_mock_client


def _payload_monthly() -> dict:
    return {
        "description": {"title": "CPIH all items", "unit": "Index", "releaseDate": "2026-04-17"},
        "months": [
            {"date": "2026 JAN", "value": "132.5"},
            {"date": "2026 FEB", "value": "132.8"},
            {"date": "2026 MAR", "value": ""},
        ],
        "quarters": [],
        "years": [],
    }


async def test_get_timeseries_monthly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "MM23" in request.url.path
        assert "L522" in request.url.path
        return httpx.Response(200, json=_payload_monthly())

    async with make_mock_client(handler) as client:
        ts = await ons.get_timeseries("MM23", "L522", client=client)

    assert ts.frequency == "monthly"
    assert ts.name == "CPIH all items"
    assert [p.date for p in ts.points] == [
        date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1),
    ]
    assert [p.value for p in ts.points] == [132.5, 132.8, None]


async def test_get_timeseries_falls_back_to_quarterly() -> None:
    payload = {
        "description": {"title": "GDP", "unit": "GBP m"},
        "months": [],
        "quarters": [
            {"date": "2026 Q1", "value": "550000"},
            {"date": "2026 Q2", "value": "551000"},
        ],
        "years": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with make_mock_client(handler) as client:
        ts = await ons.get_timeseries("UKEA", "ABMI", client=client)

    assert ts.frequency == "quarterly"
    assert [p.date for p in ts.points] == [date(2026, 1, 1), date(2026, 4, 1)]
