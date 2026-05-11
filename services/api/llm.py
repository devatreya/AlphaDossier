"""Anthropic Claude wrapper for structured agent output.

Phase 4 agents always need a typed object back, so the public entry point is
`complete_structured` which uses Anthropic tool-use to force the model to emit
JSON matching a Pydantic schema. The free-form `complete` function is kept for
synthesis-style use cases where the answer is prose.

Cost estimation is best-effort: we use the published per-1M-token rates for the
model families we expect to use. Unknown models return None so audit rows can
still be written without lying about cost.
"""
from __future__ import annotations

import time
from typing import Any, TypeVar

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from .config import get_settings
from .data._errors import ConnectorError, MissingApiKeyError

T = TypeVar("T", bound=BaseModel)

PROVIDER = "anthropic"
TOOL_NAME = "submit_analysis"


class LLMError(ConnectorError):
    pass


class LLMRequest(BaseModel):
    model: str
    system: str
    user: str
    max_tokens: int = 4096
    temperature: float = 0.0


class LLMResponse(BaseModel):
    text: str
    parsed: dict[str, Any] | None = None
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None = None
    cost_usd: float | None = None
    latency_ms: int
    raw: dict[str, Any] = Field(default_factory=dict)


# Per-1M-token rates ($USD). Refine as Anthropic publishes updates.
# Family-prefix match: longest prefix wins.
_RATES_USD_PER_M: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    matches = [k for k in _RATES_USD_PER_M if k in model]
    if not matches:
        return None
    key = max(matches, key=len)
    in_rate, out_rate = _RATES_USD_PER_M[key]
    return round(
        input_tokens / 1_000_000 * in_rate + output_tokens / 1_000_000 * out_rate,
        6,
    )


def _get_client() -> AsyncAnthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise MissingApiKeyError("ANTHROPIC_API_KEY", provider=PROVIDER)
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _extract_tool_use_input(content: list) -> dict[str, Any]:
    """Find the tool_use block in an Anthropic response and return its input dict."""
    for block in content:
        # The SDK returns objects with .type/.input attrs; some test stubs use dicts.
        if isinstance(block, dict):
            if block.get("type") == "tool_use" and block.get("name") == TOOL_NAME:
                return dict(block.get("input") or {})
        else:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == TOOL_NAME:
                return dict(getattr(block, "input", {}) or {})
    raise LLMError(
        "Model did not call the structured-output tool; check prompt and tool_choice.",
        provider=PROVIDER,
    )


async def complete_structured(
    request: LLMRequest,
    schema: type[T],
    *,
    client: AsyncAnthropic | None = None,
) -> tuple[T, LLMResponse]:
    """Call Claude and parse the response as `schema` via tool-use.

    Returns (validated_pydantic_object, full_response). The full response carries
    token usage and latency for audit logging. Internally created clients are
    closed before returning so we don't leak HTTP pools across agent runs.
    """
    owned = client is None
    c = client or _get_client()
    try:
        tool = {
            "name": TOOL_NAME,
            "description": (
                "Submit your analysis. Use ONLY this tool to respond — do not write "
                "free-form text. All claims must be grounded in the provided context."
            ),
            "input_schema": schema.model_json_schema(),
        }

        start = time.monotonic()
        response = await c.messages.create(  # type: ignore[call-overload]
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=request.system,
            messages=[{"role": "user", "content": request.user}],
            tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME},
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        parsed_input = _extract_tool_use_input(response.content)
        obj = schema.model_validate(parsed_input)

        usage = getattr(response, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) if usage is not None else 0
        out_tok = getattr(usage, "output_tokens", 0) if usage is not None else 0
        model = getattr(response, "model", request.model)
        stop_reason = getattr(response, "stop_reason", None)

        return obj, LLMResponse(
            text=str(parsed_input),
            parsed=parsed_input,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            stop_reason=stop_reason,
            cost_usd=estimate_cost_usd(model, in_tok, out_tok),
            latency_ms=latency_ms,
            raw={
                "tool_name": TOOL_NAME,
                "tool_input": parsed_input,
                "stop_reason": stop_reason,
                "model": model,
            },
        )
    finally:
        if owned:
            await c.close()


async def complete(
    request: LLMRequest,
    *,
    client: AsyncAnthropic | None = None,
) -> LLMResponse:
    """Free-form completion — used by the synthesizer for prose output.

    Prefer `complete_structured` whenever the downstream code needs typed fields.
    """
    owned = client is None
    c = client or _get_client()
    try:
        start = time.monotonic()
        response = await c.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=request.system,
            messages=[{"role": "user", "content": request.user}],
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        text_parts: list[str] = []
        for block in response.content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text") or "")
            elif getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", "") or "")

        usage = getattr(response, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) if usage is not None else 0
        out_tok = getattr(usage, "output_tokens", 0) if usage is not None else 0
        model = getattr(response, "model", request.model)
        stop_reason = getattr(response, "stop_reason", None)
        text = "\n".join(text_parts)

        return LLMResponse(
            text=text,
            parsed=None,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            stop_reason=stop_reason,
            cost_usd=estimate_cost_usd(model, in_tok, out_tok),
            latency_ms=latency_ms,
            raw={
                "text": text,
                "stop_reason": stop_reason,
                "model": model,
            },
        )
    finally:
        if owned:
            await c.close()
