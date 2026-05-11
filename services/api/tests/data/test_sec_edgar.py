from __future__ import annotations

import httpx
import pytest

from services.api.data import sec_edgar

from .conftest import make_mock_client


@pytest.fixture(autouse=True)
def _reset_sec_cache() -> None:
    sec_edgar._reset_ticker_cache()


def _ticker_payload() -> dict:
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corp"},
    }


def _submissions_payload() -> dict:
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000320193-26-000010",
                    "0000320193-25-000099",
                    "0000320193-25-000050",
                ],
                "filingDate": ["2026-01-30", "2025-10-30", "2025-08-01"],
                "form": ["10-Q", "10-K", "8-K"],
                "primaryDocument": [
                    "aapl-20251231.htm",
                    "aapl-20250930.htm",
                    "aapl-8k.htm",
                ],
                "primaryDocDescription": ["10-Q Q1", "10-K FY25", "8-K item 2.02"],
            }
        },
    }


async def test_resolve_cik(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "company_tickers.json" in request.url.path:
            return httpx.Response(200, json=_ticker_payload())
        return httpx.Response(404)

    async with make_mock_client(handler) as client:
        cik = await sec_edgar.resolve_cik("aapl", client=client)
    assert cik == "0000320193"


async def test_recent_filings_filters_forms() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "company_tickers.json" in request.url.path:
            return httpx.Response(200, json=_ticker_payload())
        if "/submissions/CIK" in request.url.path:
            assert "0000320193" in request.url.path
            assert "User-Agent" in request.headers
            return httpx.Response(200, json=_submissions_payload())
        return httpx.Response(404)

    async with make_mock_client(handler) as client:
        filings = await sec_edgar.get_recent_filings(
            "AAPL", forms=("10-K", "10-Q"), limit=10, client=client
        )

    assert {f.form for f in filings} == {"10-K", "10-Q"}
    assert all(f.cik == "0000320193" for f in filings)
    # archive URL builder strips dashes from accession.
    aapl_10k = next(f for f in filings if f.form == "10-K")
    assert "000032019325000099" in aapl_10k.primary_doc_url
    assert aapl_10k.primary_doc_url.endswith("aapl-20250930.htm")


async def test_resolve_cik_dotted_class_share() -> None:
    """SEC publishes BRK-B; users commonly type BRK.B. Both must resolve."""
    payload = {
        "0": {"cik_str": 1067983, "ticker": "BRK-B", "title": "Berkshire Hathaway B"},
        "1": {"cik_str": 14693, "ticker": "BF-B", "title": "Brown-Forman B"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with make_mock_client(handler) as client:
        cik_dashed = await sec_edgar.resolve_cik("BRK-B", client=client)
        cik_dotted = await sec_edgar.resolve_cik("BRK.B", client=client)
        cik_lower = await sec_edgar.resolve_cik("brk.b", client=client)
        cik_bf = await sec_edgar.resolve_cik("BF.B", client=client)

    assert cik_dashed == "0001067983"
    assert cik_dotted == "0001067983"
    assert cik_lower == "0001067983"
    assert cik_bf == "0000014693"


async def test_recent_filings_unknown_ticker_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "company_tickers.json" in request.url.path:
            return httpx.Response(200, json=_ticker_payload())
        return httpx.Response(404)

    async with make_mock_client(handler) as client:
        with pytest.raises(sec_edgar.ConnectorError, match="No CIK"):
            await sec_edgar.get_recent_filings("XYZNOTREAL", client=client)
