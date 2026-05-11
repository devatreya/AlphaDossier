"""Quant validation — basic risk/regime sanity checks. No LLM call.

Builds on `price_agent.run()` and applies threshold rules:
  * Annualised volatility > 40%   → risk flag
  * Drawdown in window worse than -20%   → risk flag
  * |3m return| >= 10%   → momentum sanity check
  * |3m relative perf| >= 5%   → benchmark divergence check
  * Bars < 60 OR stale last bar (> 7 days)   → limitation

Output keeps the schema specified in the project plan so the orchestrator can
slot it into the dossier without further mapping.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from ..data._types import PriceSeries
from . import price_agent

AGENT_NAME = "quant_validation_agent"

_HIGH_VOL_THRESHOLD = 0.40
_LARGE_DRAWDOWN_THRESHOLD = -0.20
_MOMENTUM_THRESHOLD = 0.10
_REL_PERF_THRESHOLD = 0.05
_STALE_DAYS = 7


class QuantValidationOutput(BaseModel):
    available: bool
    summary: str
    metrics: dict[str, float | None] = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)
    sanity_checks: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _pct(value: float | None) -> str:
    return f"{value * 100:+.1f}%" if value is not None else "n/a"


async def run(
    series: PriceSeries,
    *,
    benchmark: PriceSeries | None = None,
    today: date | None = None,
) -> QuantValidationOutput:
    today = today or date.today()
    price = await price_agent.run(series, benchmark=benchmark, today=today)

    if price.bars_count == 0:
        return QuantValidationOutput(
            available=False,
            summary="Insufficient data: no price bars available.",
            limitations=["no price data"],
        )

    metrics: dict[str, float | None] = {
        "one_month_return": price.returns.get("1m"),
        "three_month_return": price.returns.get("3m"),
        "six_month_return": price.returns.get("6m"),
        "one_year_return": price.returns.get("1y"),
        "volatility": price.volatility_annualised,
        "max_drawdown": price.max_drawdown,
    }

    risk_flags: list[str] = []
    sanity_checks: list[str] = []
    limitations: list[str] = []

    if (vol := price.volatility_annualised) is not None and vol > _HIGH_VOL_THRESHOLD:
        risk_flags.append(f"High annualised volatility: {vol * 100:.1f}%")

    if (mdd := price.max_drawdown) is not None and mdd < _LARGE_DRAWDOWN_THRESHOLD:
        risk_flags.append(f"Large drawdown observed: {mdd * 100:.1f}%")

    r3m = price.returns.get("3m")
    if r3m is not None and abs(r3m) >= _MOMENTUM_THRESHOLD:
        direction = "Positive" if r3m > 0 else "Negative"
        sanity_checks.append(f"{direction} 3m momentum: {_pct(r3m)}")

    rel_3m = price.relative_performance.get("3m")
    if rel_3m is not None and abs(rel_3m) >= _REL_PERF_THRESHOLD:
        verb = "Outperforming" if rel_3m > 0 else "Underperforming"
        sanity_checks.append(f"{verb} benchmark by {_pct(rel_3m)} over 3m")

    if price.data_quality == "limited":
        limitations.append(
            f"Limited price history ({price.bars_count} bars; metrics may be unstable)"
        )

    if price.last_date is not None and (today - price.last_date).days > _STALE_DAYS:
        limitations.append(
            f"Stale price data: last bar {price.last_date.isoformat()} "
            f"(> {_STALE_DAYS} days from {today.isoformat()})"
        )

    return QuantValidationOutput(
        available=True,
        summary=price.summary,
        metrics=metrics,
        risk_flags=risk_flags,
        sanity_checks=sanity_checks,
        limitations=limitations,
    )


def to_audit_payload(output: QuantValidationOutput) -> dict[str, Any]:
    """Compact dict suitable for inclusion in audit_log payloads."""
    return output.model_dump(mode="json")
