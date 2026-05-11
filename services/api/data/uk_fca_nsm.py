"""FCA National Storage Mechanism (NSM) — Phase 2 stub.

The FCA NSM is the official UK repository of regulated disclosures, but it has
no free machine-readable API: the public surface is a search UI at
https://data.fca.org.uk/#/nsm/nationalstoragemechanism backed by an internal
endpoint that requires session cookies and JS to obtain.

Until we add a scraper or a licensed feed, this connector is a no-op that
returns an empty list and a `data_quality: 'unavailable'` flag for the audit
log. Phase 4 agents must treat absence of NSM results as 'not yet implemented',
not 'no disclosures'.
"""
from __future__ import annotations

from datetime import date

import httpx

from ._types import RawDocument

PROVIDER = "fca_nsm"
DATA_QUALITY = "unavailable"


async def search_nsm(
    ticker: str,
    *,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[RawDocument]:
    """Returns []. Kept as an awaitable so the orchestrator interface is uniform."""
    _ = (ticker, company_name, from_date, to_date, client)
    return []


def coverage_note() -> dict[str, str]:
    """Audit-log payload describing why NSM returned nothing."""
    return {
        "provider": PROVIDER,
        "data_quality": DATA_QUALITY,
        "reason": "FCA NSM has no free public API; awaiting scraper or licensed feed.",
    }
