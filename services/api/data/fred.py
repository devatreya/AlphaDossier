"""FRED (St. Louis Fed) connector.

Docs: https://fred.stlouisfed.org/docs/api/fred/

Used by the macro_agent. Free key required.
"""
from __future__ import annotations

from datetime import date

import httpx

from ..config import get_settings
from ._errors import MissingApiKeyError
from ._http import make_client, request_json
from ._types import TimeSeries, TimeSeriesPoint

PROVIDER = "fred"
BASE_URL = "https://api.stlouisfed.org/fred"


def _parse_value(raw: str) -> float | None:
    # FRED uses '.' for missing observations.
    if raw == "." or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def get_series_observations(
    series_id: str,
    *,
    observation_start: date | None = None,
    observation_end: date | None = None,
    client: httpx.AsyncClient | None = None,
) -> TimeSeries:
    """Fetch observations for a FRED series_id, e.g. 'DGS10', 'CPIAUCSL'."""
    settings = get_settings()
    if not settings.fred_api_key:
        raise MissingApiKeyError("FRED_API_KEY", provider=PROVIDER)

    params: dict[str, str] = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
    }
    if observation_start:
        params["observation_start"] = observation_start.isoformat()
    if observation_end:
        params["observation_end"] = observation_end.isoformat()

    owned = client is None
    c = client or make_client()
    try:
        obs_payload = await request_json(
            c, "GET", f"{BASE_URL}/series/observations", params=params, provider=PROVIDER
        )
        info_payload = await request_json(
            c,
            "GET",
            f"{BASE_URL}/series",
            params={"series_id": series_id, "api_key": settings.fred_api_key, "file_type": "json"},
            provider=PROVIDER,
        )
    finally:
        if owned:
            await c.aclose()

    info = (info_payload.get("seriess") or [{}])[0]
    points = [
        TimeSeriesPoint(date=date.fromisoformat(o["date"]), value=_parse_value(o["value"]))
        for o in obs_payload.get("observations", [])
    ]
    return TimeSeries(
        series_id=series_id,
        provider=PROVIDER,
        name=info.get("title"),
        units=info.get("units"),
        frequency=info.get("frequency"),
        points=points,
        metadata={
            "seasonal_adjustment": info.get("seasonal_adjustment_short"),
            "last_updated": info.get("last_updated"),
        },
    )
