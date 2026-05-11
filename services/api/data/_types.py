"""Shared Pydantic types for data connectors.

Document-style sources (filings, news, IR pages, RNS) return list[RawDocument].
Time-series sources (FRED, ONS) return TimeSeries. Prices return PriceSeries.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Region = Literal["US", "UK", "OTHER"]
AssetClass = Literal["equity", "etf", "index", "bond", "other"]


class Instrument(BaseModel):
    ticker: str
    region: Region
    asset_class: AssetClass
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawDocument(BaseModel):
    """A fetched textual artifact ready for chunking in Phase 3."""

    kind: str
    """Source-document type, e.g. 'sec_10k', 'sec_8k', 'rns', 'news', 'ir_html'."""

    provider: str
    """Connector that produced this, e.g. 'sec_edgar', 'news_api', 'lse_rns'."""

    url: str | None = None
    title: str | None = None
    published_at: datetime | None = None
    text: str = ""
    """Plain text suitable for chunking. May be empty if only metadata was fetched."""

    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimeSeriesPoint(BaseModel):
    date: date
    value: float | None = None


class TimeSeries(BaseModel):
    series_id: str
    provider: str
    name: str | None = None
    units: str | None = None
    frequency: str | None = None
    points: list[TimeSeriesPoint] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PriceBar(BaseModel):
    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


class PriceSeries(BaseModel):
    ticker: str
    provider: str
    currency: str | None = None
    bars: list[PriceBar] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FilingRef(BaseModel):
    """Lightweight pointer to a filing — full text fetched on demand in Phase 3."""

    cik: str
    accession_number: str
    form: str
    filing_date: date
    primary_document: str
    primary_doc_url: str
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
