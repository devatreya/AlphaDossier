"""Resolve a user-supplied ticker into region + asset_class.

Pure logic, no network calls. The Phase 4 orchestrator uses the resolved region
to decide which connectors to invoke (SEC vs RNS, FRED vs ONS).
"""
from __future__ import annotations

import re

from ._types import AssetClass, Instrument, Region

# Hand-curated lists for tickers without an exchange suffix.
# Extend as the demo set grows.
_KNOWN_US_ETFS: frozenset[str] = frozenset(
    {
        "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "VXUS", "EFA", "EEM",
        "TLT", "IEF", "SHY", "HYG", "LQD", "AGG", "BND",
        "GLD", "SLV", "USO", "UNG",
        "XLF", "XLE", "XLK", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC",
    }
)

_KNOWN_UK_ETFS: frozenset[str] = frozenset(
    {"VUKE.L", "ISF.L", "VWRL.L", "VUSA.L"}
)

# Regex: optional leading caret = index, base = letters/digits/dot/dash, optional .EXCHANGE.
_TICKER_RE = re.compile(r"^\^?[A-Z0-9.\-]{1,15}$")

_UK_SUFFIXES = (".L", ".LON")


def normalise_ticker(raw: str) -> str:
    """Uppercase, strip whitespace. Does not validate — see is_valid_ticker."""
    return raw.strip().upper()


def is_valid_ticker(ticker: str) -> bool:
    return bool(_TICKER_RE.match(ticker))


def _detect_region(ticker: str) -> Region:
    if ticker.endswith(_UK_SUFFIXES):
        return "UK"
    if ticker.startswith("^"):
        # Indexes — region depends on the index, default to OTHER for now.
        if ticker in {"^FTSE", "^FTMC", "^FTAS"}:
            return "UK"
        if ticker in {"^GSPC", "^DJI", "^IXIC", "^RUT", "^VIX"}:
            return "US"
        return "OTHER"
    return "US"


def _detect_asset_class(ticker: str) -> AssetClass:
    if ticker.startswith("^"):
        return "index"
    if ticker in _KNOWN_US_ETFS or ticker in _KNOWN_UK_ETFS:
        return "etf"
    return "equity"


def resolve(raw_ticker: str) -> Instrument:
    """Resolve a raw user input string into an Instrument.

    Raises ValueError on malformed tickers.
    """
    ticker = normalise_ticker(raw_ticker)
    if not is_valid_ticker(ticker):
        raise ValueError(f"Invalid ticker format: {raw_ticker!r}")
    return Instrument(
        ticker=ticker,
        region=_detect_region(ticker),
        asset_class=_detect_asset_class(ticker),
    )


def stripped_symbol(ticker: str) -> str:
    """Return the bare symbol without exchange suffix or ^ prefix.

    Useful for News API queries where 'SHEL.L' would not match articles that
    use just 'SHEL' or the company name.
    """
    bare = ticker.lstrip("^")
    for suffix in _UK_SUFFIXES:
        if bare.endswith(suffix):
            return bare[: -len(suffix)]
    return bare
