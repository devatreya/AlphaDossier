"""SEC EDGAR connector.

Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces

No API key, but the SEC fair-access policy requires a descriptive User-Agent
with contact info — set via SEC_USER_AGENT in .env.

Endpoints used here:
  - https://www.sec.gov/files/company_tickers.json   ticker -> CIK mapping
  - https://data.sec.gov/submissions/CIK{cik:010d}.json   recent filings
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Iterable

import httpx

from ..config import get_settings
from ._errors import ConnectorError
from ._http import make_client, request_json
from ._types import FilingRef

PROVIDER = "sec_edgar"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_no_dashless}/{primary_doc}"

DEFAULT_FORMS: tuple[str, ...] = ("10-K", "10-Q", "8-K", "20-F", "6-K")

# Module-level caches: SEC ticker mapping is ~1MB and changes rarely.
_ticker_cache: dict[str, str] | None = None
_ticker_cache_lock = asyncio.Lock()


def _sec_headers() -> dict[str, str]:
    return {
        "User-Agent": get_settings().sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


def _pad_cik(cik: int | str) -> str:
    return str(int(cik)).zfill(10)


async def _load_ticker_map(client: httpx.AsyncClient) -> dict[str, str]:
    """Lazy-load the SEC ticker → CIK map. Cached for the process lifetime."""
    global _ticker_cache
    async with _ticker_cache_lock:
        if _ticker_cache is not None:
            return _ticker_cache
        payload = await request_json(
            client, "GET", TICKERS_URL, headers=_sec_headers(), provider=PROVIDER
        )
        # Payload shape: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."}, ...}
        # SEC publishes class-share tickers with dashes (BRK-B, BF-B), but users
        # commonly type the dotted form (BRK.B). Register both so either resolves.
        mapping: dict[str, str] = {}
        for entry in payload.values():
            ticker = str(entry.get("ticker", "")).upper()
            cik = entry.get("cik_str")
            if not ticker or cik is None:
                continue
            padded = _pad_cik(cik)
            mapping[ticker] = padded
            if "-" in ticker:
                mapping[ticker.replace("-", ".")] = padded
        _ticker_cache = mapping
        return mapping


def _reset_ticker_cache() -> None:
    """Test hook to clear the in-process cache."""
    global _ticker_cache
    _ticker_cache = None


async def resolve_cik(
    ticker: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Map a US ticker to its zero-padded 10-digit CIK string. Returns None if unknown."""
    owned = client is None
    c = client or make_client()
    try:
        mapping = await _load_ticker_map(c)
    finally:
        if owned:
            await c.aclose()
    return mapping.get(ticker.upper())


def _build_archive_url(cik: str, accession_number: str, primary_doc: str) -> str:
    return ARCHIVES_URL.format(
        cik_int=int(cik),
        accession_no_dashless=accession_number.replace("-", ""),
        primary_doc=primary_doc,
    )


async def get_recent_filings(
    ticker: str,
    *,
    forms: Iterable[str] = DEFAULT_FORMS,
    limit: int = 20,
    client: httpx.AsyncClient | None = None,
) -> list[FilingRef]:
    """Return up to `limit` recent filings for `ticker`, filtered to `forms`.

    Raises ConnectorError if the ticker cannot be resolved to a CIK (likely a
    non-US ticker — caller should route to the UK disclosure connectors).
    """
    forms_set = {f.upper() for f in forms}
    owned = client is None
    c = client or make_client()
    try:
        cik = (await _load_ticker_map(c)).get(ticker.upper())
        if cik is None:
            raise ConnectorError(
                f"No CIK for ticker {ticker!r}; not a US-listed issuer?",
                provider=PROVIDER,
            )
        payload = await request_json(
            c,
            "GET",
            SUBMISSIONS_URL.format(cik=cik),
            headers=_sec_headers(),
            provider=PROVIDER,
        )
    finally:
        if owned:
            await c.aclose()

    recent = (payload.get("filings") or {}).get("recent") or {}
    accession = recent.get("accessionNumber") or []
    forms_arr = recent.get("form") or []
    dates = recent.get("filingDate") or []
    primary_docs = recent.get("primaryDocument") or []
    titles = recent.get("primaryDocDescription") or []

    out: list[FilingRef] = []
    for i, form in enumerate(forms_arr):
        if form.upper() not in forms_set:
            continue
        if i >= len(accession) or i >= len(dates) or i >= len(primary_docs):
            break
        try:
            filing_date = date.fromisoformat(dates[i])
        except ValueError:
            continue
        out.append(
            FilingRef(
                cik=cik,
                accession_number=accession[i],
                form=form,
                filing_date=filing_date,
                primary_document=primary_docs[i],
                primary_doc_url=_build_archive_url(cik, accession[i], primary_docs[i]),
                title=titles[i] if i < len(titles) else None,
                metadata={"company_name": payload.get("name")},
            )
        )
        if len(out) >= limit:
            break
    return out
