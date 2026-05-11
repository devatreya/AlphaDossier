"""UK RNS (Regulatory News Service) connector — proxy implementation.

There is no free, ToS-clean public API for RNS. For the MVP we proxy via News
API filtered to RNS-publishing domains (Investegate, LSE, MarketWatch RNS feed,
etc.) and clearly mark the documents as `kind='rns_proxy'` so downstream
agents know they are not reading the raw regulated source.

Phase 2 limit: this is a recall-not-precision proxy. Some RNS items will be
missed; some non-RNS articles may be returned. A licensed feed (Refinitiv,
LSEG RNS Distribution) replaces this in production.
"""
from __future__ import annotations

from datetime import date

import httpx

from . import news_api
from ._types import RawDocument
from .identifiers import stripped_symbol

PROVIDER = "uk_rns_proxy"

# Domains known to republish or aggregate RNS announcements.
_RNS_PROXY_DOMAINS: tuple[str, ...] = (
    "investegate.co.uk",
    "londonstockexchange.com",
    "lseg.com",
    "rns-pdf.londonstockexchange.com",
)


async def search_rns(
    ticker: str,
    *,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    page_size: int = 25,
    client: httpx.AsyncClient | None = None,
) -> list[RawDocument]:
    """Search News API filtered to RNS-publishing domains.

    Constructs a query that combines the bare symbol and (optionally) the
    company name, since RNS items often reference the issuer by name only.
    """
    symbol = stripped_symbol(ticker)
    parts = [f'"{symbol}"']
    if company_name:
        parts.append(f'"{company_name}"')
    query = " OR ".join(parts)

    docs = await news_api.search_everything(
        query,
        from_date=from_date,
        to_date=to_date,
        page_size=page_size,
        domains=_RNS_PROXY_DOMAINS,
        client=client,
    )
    # Re-tag so the orchestrator and audit log can distinguish from generic news.
    for d in docs:
        d.kind = "rns_proxy"
        d.provider = PROVIDER
        d.metadata.setdefault("note", "RNS proxy via News API; not the regulated source.")
    return docs
