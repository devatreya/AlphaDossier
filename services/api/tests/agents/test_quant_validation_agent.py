from __future__ import annotations

from datetime import date, timedelta

from services.api.agents import quant_validation_agent
from services.api.data._types import PriceBar, PriceSeries


def _series(closes: list[float], *, end: date) -> PriceSeries:
    bars = []
    for i, c in enumerate(reversed(closes)):
        d = end - timedelta(days=i)
        bars.append(PriceBar(date=d, open=c, high=c, low=c, close=c, volume=1_000))
    bars.reverse()
    return PriceSeries(ticker="X", provider="yfinance", currency="USD", bars=bars)


async def test_no_data_marks_unavailable() -> None:
    out = await quant_validation_agent.run(PriceSeries(ticker="X", provider="yfinance"))
    assert out.available is False
    assert "no price data" in out.limitations[0]


async def test_high_volatility_flagged() -> None:
    end = date(2026, 4, 30)
    # Alternating large daily moves => high volatility.
    closes = [100.0]
    for i in range(120):
        closes.append(closes[-1] * (1.05 if i % 2 else 0.95))
    out = await quant_validation_agent.run(_series(closes, end=end), today=end)
    assert out.available
    assert any("High annualised volatility" in f for f in out.risk_flags)


async def test_large_drawdown_flagged() -> None:
    end = date(2026, 4, 30)
    closes = [100.0] * 60 + [70.0] * 60  # 30% drawdown
    out = await quant_validation_agent.run(_series(closes, end=end), today=end)
    assert out.available
    assert any("Large drawdown" in f for f in out.risk_flags)


async def test_momentum_check() -> None:
    end = date(2026, 4, 30)
    closes = [100 + 0.5 * i for i in range(120)]  # steady uptrend
    out = await quant_validation_agent.run(_series(closes, end=end), today=end)
    assert any("3m momentum" in s for s in out.sanity_checks)


async def test_relative_perf_check_against_benchmark() -> None:
    end = date(2026, 4, 30)
    ticker = _series([100 + i for i in range(120)], end=end)
    bench = _series([100 + 0.2 * i for i in range(120)], end=end)
    out = await quant_validation_agent.run(ticker, benchmark=bench, today=end)
    assert any("Outperforming" in s for s in out.sanity_checks)


async def test_stale_data_limitation() -> None:
    end = date(2026, 4, 30)
    closes = [100 + 0.1 * i for i in range(120)]
    series = _series(closes, end=end - timedelta(days=14))
    out = await quant_validation_agent.run(series, today=end)
    assert any("Stale price data" in lim for lim in out.limitations)


async def test_limited_history() -> None:
    end = date(2026, 4, 30)
    out = await quant_validation_agent.run(_series([100, 101, 102, 103, 104], end=end), today=end)
    assert out.available
    assert any("Limited price history" in lim for lim in out.limitations)
