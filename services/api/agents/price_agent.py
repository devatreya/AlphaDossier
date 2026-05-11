"""Price agent — pure stats over a PriceSeries. No LLM call.

Computes return windows, annualised volatility, and max drawdown. Optional
benchmark series gives relative performance over the same windows.

Output is consumed by Phase 4 quant_validation_agent and the synthesizer's
price/risk sanity-check section.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import pstdev
from typing import Literal

from pydantic import BaseModel, Field

from ..data._types import PriceSeries

DataQuality = Literal["good", "limited", "missing"]

# Approximate trading days per year for annualising daily vol.
_TRADING_DAYS_PER_YEAR = 252

_RETURN_WINDOWS: tuple[tuple[str, int], ...] = (
    ("1m", 30),
    ("3m", 90),
    ("6m", 180),
    ("1y", 365),
    ("ytd", 0),  # special-cased below
)

# Bars below this lose statistical meaning; mark data_quality limited.
_MIN_BARS_GOOD = 60


class PriceAgentOutput(BaseModel):
    summary: str
    bars_count: int
    first_date: date | None = None
    last_date: date | None = None
    last_close: float | None = None
    currency: str | None = None
    returns: dict[str, float | None] = Field(default_factory=dict)
    volatility_annualised: float | None = None
    max_drawdown: float | None = None
    relative_performance: dict[str, float | None] = Field(default_factory=dict)
    data_quality: DataQuality = "missing"
    notes: list[str] = Field(default_factory=list)


def _close_at_or_before(
    series: PriceSeries, target: date
) -> tuple[date, float] | None:
    """Last close on or before `target`. Returns None if no bar qualifies."""
    last: tuple[date, float] | None = None
    for bar in series.bars:
        if bar.close is None:
            continue
        if bar.date <= target:
            last = (bar.date, bar.close)
        else:
            break
    return last


def _last_close(series: PriceSeries) -> tuple[date, float] | None:
    for bar in reversed(series.bars):
        if bar.close is not None:
            return (bar.date, bar.close)
    return None


def _window_return(
    series: PriceSeries, *, days: int, today: date
) -> float | None:
    last = _last_close(series)
    if last is None:
        return None
    end_date, end_close = last
    if days == 0:
        # YTD: return from the last close on or before Jan 1 of the same year.
        start_target = date(end_date.year, 1, 1) - timedelta(days=1)
    else:
        start_target = end_date - timedelta(days=days)
    start = _close_at_or_before(series, start_target)
    if start is None:
        return None
    _, start_close = start
    if start_close == 0:
        return None
    return round((end_close / start_close) - 1.0, 6)


def _daily_log_returns(series: PriceSeries) -> list[float]:
    closes = [b.close for b in series.bars if b.close is not None and b.close > 0]
    out: list[float] = []
    for prev, curr in zip(closes, closes[1:], strict=False):
        out.append(math.log(curr / prev))
    return out


def _annualised_volatility(series: PriceSeries) -> float | None:
    rets = _daily_log_returns(series)
    if len(rets) < 5:
        return None
    sd = pstdev(rets)
    return round(sd * math.sqrt(_TRADING_DAYS_PER_YEAR), 6)


def _max_drawdown(series: PriceSeries) -> float | None:
    closes = [b.close for b in series.bars if b.close is not None]
    if len(closes) < 2:
        return None
    peak = closes[0]
    worst = 0.0
    for c in closes[1:]:
        peak = max(peak, c)
        if peak <= 0:
            continue
        dd = (c / peak) - 1.0
        worst = min(worst, dd)
    return round(worst, 6) if worst < 0 else 0.0


def _summarise(
    bars_count: int,
    last_close: float | None,
    currency: str | None,
    returns: dict[str, float | None],
    vol: float | None,
    mdd: float | None,
    quality: DataQuality,
) -> str:
    if bars_count == 0:
        return "No price history available."
    parts = [f"{bars_count} daily bars"]
    if last_close is not None:
        parts.append(f"last close {last_close:.2f}{f' {currency}' if currency else ''}")
    if (r3m := returns.get("3m")) is not None:
        parts.append(f"3m return {r3m * 100:+.1f}%")
    if (r1y := returns.get("1y")) is not None:
        parts.append(f"1y return {r1y * 100:+.1f}%")
    if vol is not None:
        parts.append(f"ann. vol {vol * 100:.1f}%")
    if mdd is not None and mdd < 0:
        parts.append(f"max drawdown {mdd * 100:.1f}%")
    if quality != "good":
        parts.append(f"data quality: {quality}")
    return "; ".join(parts) + "."


async def run(
    series: PriceSeries,
    *,
    benchmark: PriceSeries | None = None,
    today: date | None = None,
) -> PriceAgentOutput:
    today = today or date.today()
    if not series.bars:
        return PriceAgentOutput(
            summary="No price history available.",
            bars_count=0,
            data_quality="missing",
        )

    # Bars are persisted in date-asc order; defensive resort here is cheap.
    bars_sorted = sorted(series.bars, key=lambda b: b.date)
    sorted_series = series.model_copy(update={"bars": bars_sorted})

    bars_count = len(sorted_series.bars)
    quality: DataQuality = "good" if bars_count >= _MIN_BARS_GOOD else "limited"

    last = _last_close(sorted_series)
    last_close = last[1] if last else None
    last_date = last[0] if last else None
    first_date = next((b.date for b in sorted_series.bars if b.close is not None), None)

    returns = {
        label: _window_return(sorted_series, days=days, today=today)
        for label, days in _RETURN_WINDOWS
    }
    vol = _annualised_volatility(sorted_series)
    mdd = _max_drawdown(sorted_series)

    relative: dict[str, float | None] = {}
    notes: list[str] = []
    if benchmark is not None and benchmark.bars:
        sorted_bench = benchmark.model_copy(
            update={"bars": sorted(benchmark.bars, key=lambda b: b.date)}
        )
        for label, days in _RETURN_WINDOWS:
            ticker_ret = returns[label]
            bench_ret = _window_return(sorted_bench, days=days, today=today)
            if ticker_ret is None or bench_ret is None:
                relative[label] = None
            else:
                relative[label] = round(ticker_ret - bench_ret, 6)
    elif benchmark is not None:
        notes.append("benchmark series was empty; relative performance unavailable")

    if bars_count < _MIN_BARS_GOOD:
        notes.append(
            f"only {bars_count} bars available; some metrics may be unstable"
        )

    summary = _summarise(bars_count, last_close, sorted_series.currency, returns, vol, mdd, quality)

    return PriceAgentOutput(
        summary=summary,
        bars_count=bars_count,
        first_date=first_date,
        last_date=last_date,
        last_close=last_close,
        currency=sorted_series.currency,
        returns=returns,
        volatility_annualised=vol,
        max_drawdown=mdd,
        relative_performance=relative,
        data_quality=quality,
        notes=notes,
    )
