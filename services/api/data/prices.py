"""Daily OHLCV price history.

Primary: Yahoo Finance chart API (public JSON, no key). yfinance is intentionally
not a dependency — we hit the same endpoint directly to keep the install lean.

Fallback: Stooq CSV downloads. Stooq has decent coverage of UK tickers under
a slightly different convention (e.g. SHEL.UK rather than SHEL.L) but is
brittle and rate-limited.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timezone

import httpx

from ._errors import ConnectorError
from ._http import make_client, request_json, request_text
from ._types import PriceBar, PriceSeries

log = logging.getLogger(__name__)

YAHOO_PROVIDER = "yfinance"
STOOQ_PROVIDER = "stooq"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
STOOQ_URL = "https://stooq.com/q/d/l/"


def _to_unix(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


_ONE_DAY_SECONDS = 86_400


def _normalise_uk_suffix(ticker: str) -> str:
    """Both .L and .LON are accepted user inputs; Yahoo uses .L only."""
    upper = ticker.upper()
    if upper.endswith(".LON"):
        return upper[:-4] + ".L"
    return upper


async def get_yahoo_history(
    ticker: str,
    *,
    start_date: date,
    end_date: date,
    interval: str = "1d",
    client: httpx.AsyncClient | None = None,
) -> PriceSeries:
    """Fetch daily OHLCV from Yahoo's chart API. Raises ConnectorError on bad data.

    Yahoo treats `period2` as exclusive, so we shift it forward by one day to
    include the requested end_date in the result set.
    """
    yahoo_ticker = _normalise_uk_suffix(ticker)
    params = {
        "period1": _to_unix(start_date),
        "period2": _to_unix(end_date) + _ONE_DAY_SECONDS,
        "interval": interval,
        "includePrePost": "false",
    }
    owned = client is None
    c = client or make_client()
    try:
        payload = await request_json(
            c, "GET", YAHOO_URL.format(ticker=yahoo_ticker), params=params,
            provider=YAHOO_PROVIDER,
        )
    finally:
        if owned:
            await c.aclose()

    chart = payload.get("chart") or {}
    err = chart.get("error")
    if err:
        raise ConnectorError(f"yahoo: {err}", provider=YAHOO_PROVIDER)
    results = chart.get("result") or []
    if not results:
        return PriceSeries(ticker=ticker, provider=YAHOO_PROVIDER)
    result = results[0]
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or [None] * len(timestamps)
    highs = quote.get("high") or [None] * len(timestamps)
    lows = quote.get("low") or [None] * len(timestamps)
    closes = quote.get("close") or [None] * len(timestamps)
    volumes = quote.get("volume") or [None] * len(timestamps)

    bars: list[PriceBar] = []
    for i, ts in enumerate(timestamps):
        bars.append(
            PriceBar(
                date=datetime.fromtimestamp(ts, tz=timezone.utc).date(),
                open=opens[i],
                high=highs[i],
                low=lows[i],
                close=closes[i],
                volume=volumes[i],
            )
        )
    return PriceSeries(
        ticker=ticker,
        provider=YAHOO_PROVIDER,
        currency=meta.get("currency"),
        bars=bars,
        metadata={
            "exchange_name": meta.get("exchangeName"),
            "instrument_type": meta.get("instrumentType"),
        },
    )


def _yahoo_to_stooq_symbol(ticker: str) -> str:
    """Yahoo uses '.L' for LSE; Stooq uses '.UK'. Pass-through for US.

    Also accepts '.LON' (which identifiers.py allows) by normalising to '.L' first.
    """
    upper = _normalise_uk_suffix(ticker)
    if upper.endswith(".L"):
        return upper[:-2].lower() + ".uk"
    return upper.lower()


async def get_stooq_history(
    ticker: str,
    *,
    start_date: date,
    end_date: date,
    client: httpx.AsyncClient | None = None,
) -> PriceSeries:
    """Fetch daily OHLCV CSV from Stooq."""
    params = {
        "s": _yahoo_to_stooq_symbol(ticker),
        "i": "d",
        "d1": start_date.strftime("%Y%m%d"),
        "d2": end_date.strftime("%Y%m%d"),
    }
    owned = client is None
    c = client or make_client()
    try:
        text = await request_text(
            c, "GET", STOOQ_URL, params=params, provider=STOOQ_PROVIDER
        )
    finally:
        if owned:
            await c.aclose()

    if not text or text.startswith("No data"):
        return PriceSeries(ticker=ticker, provider=STOOQ_PROVIDER)

    reader = csv.DictReader(io.StringIO(text))
    bars: list[PriceBar] = []
    for row in reader:
        try:
            d = date.fromisoformat(row["Date"])
        except (KeyError, ValueError):
            continue
        bars.append(
            PriceBar(
                date=d,
                open=_safe_float(row.get("Open")),
                high=_safe_float(row.get("High")),
                low=_safe_float(row.get("Low")),
                close=_safe_float(row.get("Close")),
                volume=_safe_float(row.get("Volume")),
            )
        )
    return PriceSeries(ticker=ticker, provider=STOOQ_PROVIDER, bars=bars)


def _safe_float(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


async def get_history(
    ticker: str,
    *,
    start_date: date,
    end_date: date,
    client: httpx.AsyncClient | None = None,
) -> PriceSeries:
    """Try Yahoo first, fall back to Stooq on failure or empty result."""
    try:
        series = await get_yahoo_history(
            ticker, start_date=start_date, end_date=end_date, client=client
        )
        if series.bars:
            return series
    except ConnectorError as exc:
        log.warning("Yahoo failed for %s, falling back to Stooq: %s", ticker, exc)

    return await get_stooq_history(
        ticker, start_date=start_date, end_date=end_date, client=client
    )
