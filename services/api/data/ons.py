"""ONS (Office for National Statistics) timeseries connector.

Docs: https://developer.ons.gov.uk/

The legacy timeseries endpoint accepts a CDID (e.g. 'D7G7' for CPIH) under a
parent dataset (e.g. 'MM23') and returns the full series as JSON. No API key.
"""
from __future__ import annotations

from datetime import date

import httpx

from ._http import make_client, request_json
from ._types import TimeSeries, TimeSeriesPoint

PROVIDER = "ons"
TIMESERIES_URL = "https://api.ons.gov.uk/dataset/{dataset}/timeseries/{cdid}/data"


def _parse_quarterly(label: str) -> date | None:
    # e.g. "2024 Q1"
    try:
        year_str, q = label.split()
        year = int(year_str)
        quarter = int(q.replace("Q", ""))
        month = (quarter - 1) * 3 + 1
        return date(year, month, 1)
    except ValueError:
        return None


def _parse_monthly(label: str) -> date | None:
    # e.g. "2024 JAN"
    months = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    try:
        parts = label.split()
        if len(parts) != 2:
            return None
        year = int(parts[0])
        month = months.get(parts[1].upper())
        if not month:
            return None
        return date(year, month, 1)
    except ValueError:
        return None


def _parse_annual(label: str) -> date | None:
    try:
        return date(int(label), 1, 1)
    except ValueError:
        return None


def _coerce_value(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).replace(",", ""))
    except ValueError:
        return None


def _points_from(observations: list[dict], parser) -> list[TimeSeriesPoint]:
    out: list[TimeSeriesPoint] = []
    for o in observations:
        d = parser(o.get("date") or "")
        if d is None:
            continue
        out.append(TimeSeriesPoint(date=d, value=_coerce_value(o.get("value"))))
    return out


async def get_timeseries(
    dataset: str,
    cdid: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> TimeSeries:
    """Fetch a CDID timeseries, e.g. get_timeseries('MM23', 'D7G7') for CPIH."""
    owned = client is None
    c = client or make_client()
    try:
        payload = await request_json(
            c, "GET",
            TIMESERIES_URL.format(dataset=dataset, cdid=cdid),
            provider=PROVIDER,
        )
    finally:
        if owned:
            await c.aclose()

    description = payload.get("description") or {}
    # Prefer the highest-frequency series available.
    monthly = _points_from(payload.get("months") or [], _parse_monthly)
    quarterly = _points_from(payload.get("quarters") or [], _parse_quarterly)
    annual = _points_from(payload.get("years") or [], _parse_annual)
    points, frequency = (
        (monthly, "monthly") if monthly
        else (quarterly, "quarterly") if quarterly
        else (annual, "annual")
    )
    return TimeSeries(
        series_id=cdid,
        provider=PROVIDER,
        name=description.get("title"),
        units=description.get("unit"),
        frequency=frequency,
        points=points,
        metadata={
            "dataset": dataset,
            "cdid": cdid,
            "release_date": description.get("releaseDate"),
        },
    )
