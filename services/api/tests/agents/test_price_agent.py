from __future__ import annotations

import math
from datetime import date, timedelta

from services.api.agents import price_agent
from services.api.data._types import PriceBar, PriceSeries


def _make_series(prices: list[float], *, end: date, ticker: str = "X", currency: str = "USD") -> PriceSeries:
    bars: list[PriceBar] = []
    for i, p in enumerate(reversed(prices)):
        d = end - timedelta(days=i)
        bars.append(PriceBar(date=d, open=p, high=p, low=p, close=p, volume=1_000))
    bars.reverse()
    return PriceSeries(ticker=ticker, provider="yfinance", currency=currency, bars=bars)


async def test_empty_series_returns_missing() -> None:
    out = await price_agent.run(PriceSeries(ticker="X", provider="yfinance"))
    assert out.bars_count == 0
    assert out.data_quality == "missing"
    assert out.returns == {}


async def test_returns_and_drawdown() -> None:
    end = date(2026, 4, 30)
    # 400 daily bars, simple uptrend with a synthetic drawdown
    prices = [100 + i * 0.1 for i in range(400)]
    # inject a 25% drawdown 80 days from the end
    for i in range(380, 390):
        prices[i] *= 0.75
    series = _make_series(prices, end=end)

    out = await price_agent.run(series, today=end)

    assert out.bars_count == 400
    assert out.data_quality == "good"
    assert out.last_close is not None
    assert out.returns["1y"] is not None
    assert out.returns["1m"] is not None
    assert out.max_drawdown is not None
    assert out.max_drawdown < -0.10
    assert out.volatility_annualised is not None
    assert out.volatility_annualised > 0
    assert "bars" in out.summary


async def test_relative_performance_against_benchmark() -> None:
    end = date(2026, 4, 30)
    ticker = _make_series([100 + i for i in range(120)], end=end)
    bench = _make_series([100 + 0.5 * i for i in range(120)], end=end)
    out = await price_agent.run(ticker, benchmark=bench, today=end)
    rel_3m = out.relative_performance.get("3m")
    assert rel_3m is not None
    # Ticker rose faster than benchmark, so relative should be positive.
    assert rel_3m > 0


async def test_limited_quality_under_min_bars() -> None:
    end = date(2026, 4, 30)
    series = _make_series([100, 101, 102, 103, 104, 105, 106], end=end)
    out = await price_agent.run(series, today=end)
    assert out.data_quality == "limited"
    assert any("only" in n for n in out.notes)


async def test_volatility_finite() -> None:
    end = date(2026, 4, 30)
    series = _make_series(
        [100 * (1 + 0.01 * (-1 if i % 2 else 1)) for i in range(120)],
        end=end,
    )
    out = await price_agent.run(series, today=end)
    assert out.volatility_annualised is not None
    assert math.isfinite(out.volatility_annualised)
