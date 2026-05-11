from __future__ import annotations

from datetime import date, datetime, timezone

import httpx

from services.api.data import prices

from .conftest import make_mock_client


def _yahoo_payload() -> dict:
    ts = [
        int(datetime(2026, 4, 14, tzinfo=timezone.utc).timestamp()),
        int(datetime(2026, 4, 15, tzinfo=timezone.utc).timestamp()),
    ]
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {
                        "currency": "USD",
                        "exchangeName": "NMS",
                        "instrumentType": "EQUITY",
                    },
                    "timestamp": ts,
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, 101.0],
                                "high": [102.0, 103.0],
                                "low": [99.0, 100.5],
                                "close": [101.5, 102.5],
                                "volume": [1_000_000, 1_200_000],
                            }
                        ]
                    },
                }
            ],
        }
    }


async def test_yahoo_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/v8/finance/chart/NVDA" in request.url.path
        return httpx.Response(200, json=_yahoo_payload())

    async with make_mock_client(handler) as client:
        series = await prices.get_yahoo_history(
            "NVDA",
            start_date=date(2026, 4, 14),
            end_date=date(2026, 4, 15),
            client=client,
        )

    assert series.provider == "yfinance"
    assert series.currency == "USD"
    assert len(series.bars) == 2
    assert series.bars[0].open == 100.0
    assert series.bars[1].close == 102.5


async def test_stooq_history() -> None:
    csv_body = (
        "Date,Open,High,Low,Close,Volume\n"
        "2026-04-14,100.0,102.0,99.0,101.5,1000000\n"
        "2026-04-15,101.0,103.0,100.5,102.5,1200000\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "stooq.com" in str(request.url)
        return httpx.Response(200, text=csv_body)

    async with make_mock_client(handler) as client:
        series = await prices.get_stooq_history(
            "NVDA",
            start_date=date(2026, 4, 14),
            end_date=date(2026, 4, 15),
            client=client,
        )
    assert series.provider == "stooq"
    assert len(series.bars) == 2
    assert series.bars[0].close == 101.5


def test_stooq_uk_symbol_mapping() -> None:
    assert prices._yahoo_to_stooq_symbol("SHEL.L") == "shel.uk"
    assert prices._yahoo_to_stooq_symbol("NVDA") == "nvda"


def test_stooq_lon_suffix_normalised() -> None:
    """identifiers.py accepts both .L and .LON; both must reach Stooq as .uk."""
    assert prices._yahoo_to_stooq_symbol("SHEL.LON") == "shel.uk"


async def test_yahoo_period2_includes_end_date() -> None:
    """Yahoo treats period2 as exclusive; we add a day so end_date is included."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_yahoo_payload())

    async with make_mock_client(handler) as client:
        await prices.get_yahoo_history(
            "NVDA",
            start_date=date(2026, 4, 14),
            end_date=date(2026, 4, 15),
            client=client,
        )

    p1 = int(captured["params"]["period1"])
    p2 = int(captured["params"]["period2"])
    # 14 Apr → 16 Apr midnight = 2 full days, so end_date 15 Apr is included.
    assert p2 - p1 == 2 * 86_400


async def test_yahoo_normalises_lon_suffix() -> None:
    """SHEL.LON must hit Yahoo as SHEL.L (Yahoo doesn't recognise .LON)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_yahoo_payload())

    async with make_mock_client(handler) as client:
        await prices.get_yahoo_history(
            "SHEL.LON",
            start_date=date(2026, 4, 14),
            end_date=date(2026, 4, 15),
            client=client,
        )
    assert "/v8/finance/chart/SHEL.L" in captured["path"]
    assert ".LON" not in captured["path"]


async def test_get_history_falls_back_to_stooq_on_yahoo_error() -> None:
    """When Yahoo returns 5xx-then-empty, get_history should land on Stooq."""
    csv_body = "Date,Open,High,Low,Close,Volume\n2026-04-14,1,2,3,4,5\n"
    yahoo_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "query1.finance.yahoo.com" in str(request.url):
            yahoo_calls["n"] += 1
            return httpx.Response(503)
        if "stooq.com" in str(request.url):
            return httpx.Response(200, text=csv_body)
        return httpx.Response(404)

    async with make_mock_client(handler) as client:
        series = await prices.get_history(
            "NVDA",
            start_date=date(2026, 4, 14),
            end_date=date(2026, 4, 15),
            client=client,
        )

    assert series.provider == "stooq"
    assert yahoo_calls["n"] >= 2  # initial + at least one retry
