"""Generic agent runner.

Each LLM agent calls `run_agent` with its prompt template name, a Pydantic
output schema, and the retrievals to ground on. The runner:

  1. Renders the prompt with `{ticker}`, `{focus_question}`, `{context}`, ...
  2. Calls the LLM via `complete_structured` (or an injected stub for tests).
  3. Validates the output against the schema (handled inside complete_structured).
  4. Filters any `cited_chunk_ids` field to chunk_ids that actually appear in
     the retrieval set, so the citation store never sees made-up UUIDs.
  5. Writes one `audit_log` row.

Returns the parsed Pydantic object.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Sequence, TypeVar
from uuid import UUID

from pydantic import BaseModel

from .. import audit, llm
from ..config import get_settings
from ..ingest._types import Retrieval
from ._format import format_retrievals
from ._prompts import render_prompt

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

LlmComplete = Callable[
    [llm.LLMRequest, type[BaseModel]],
    Awaitable[tuple[BaseModel, llm.LLMResponse]],
]
AuditLog = Callable[..., Awaitable[UUID | None]]

DEFAULT_SYSTEM_PROMPT = (
    "You are a financial research assistant for analysts at a hedge fund. "
    "Be precise, factual, and dispassionate. Ground every claim in the "
    "provided context. Do NOT make recommendations to buy or sell. If the "
    "context does not contain enough information for a section, return an "
    "empty list/null and explain via the optional `notes` fields."
)

def _is_citation_field(name: str) -> bool:
    """True iff `name` is a Pydantic field carrying a list of chunk-id citations.

    Matches by name suffix so per-section variants like `headline_cited_chunk_ids`,
    `summary_cited_chunk_ids`, `statement_cited_chunk_ids`, `sector_cited_chunk_ids`
    etc. are validated alongside the canonical `cited_chunk_ids`. Also accepts
    the legacy `citation_ids` name from the project plan's example schemas.
    """
    return name.endswith("chunk_ids") or name == "citation_ids"


def _filter_uuid_list(items: list[Any], existing: set[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    out: list[UUID] = []
    for cid in items:
        if cid in existing and cid not in seen:
            out.append(cid)
            seen.add(cid)
    return out


def _declares_citation_field(model: BaseModel) -> bool:
    """True iff the model's class schema includes any citation field."""
    return any(_is_citation_field(f) for f in type(model).model_fields)


def _all_citation_fields_empty(model: BaseModel) -> bool:
    """True iff every citation field on this model is empty/missing.

    Items whose schema declares a citation field but ends up with no citations
    after filtering have no support left and must be dropped — leaving them
    would let unsupported claims survive the runner.
    """
    fields = [f for f in type(model).model_fields if _is_citation_field(f)]
    if not fields:
        return False
    return all(not getattr(model, f, None) for f in fields)


def _walk_and_filter(value: Any, existing: set[UUID]) -> Any:
    """Recursively walk a Pydantic tree:

    - Replace any citation list with UUIDs that actually appear in `existing`,
      deduplicated.
    - Drop list items whose schema declares a citation field but whose
      citations went empty after filtering (unsupported claim).

    Returns the same object when nothing changed.
    """
    if isinstance(value, BaseModel):
        updates: dict[str, Any] = {}
        for field_name in type(value).model_fields:
            current = getattr(value, field_name)
            if _is_citation_field(field_name) and isinstance(current, list):
                filtered = _filter_uuid_list(current, existing)
                if filtered != current:
                    updates[field_name] = filtered
                continue
            new_val = _walk_and_filter(current, existing)
            if new_val is not current:
                updates[field_name] = new_val
        if updates:
            return value.model_copy(update=updates)
        return value
    if isinstance(value, list):
        new_list: list[Any] = []
        changed = False
        for item in value:
            new_item = _walk_and_filter(item, existing)
            if new_item is not item:
                changed = True
            if (
                isinstance(new_item, BaseModel)
                and _declares_citation_field(new_item)
                and _all_citation_fields_empty(new_item)
            ):
                # Unsupported claim — drop rather than retain with empty citation list.
                changed = True
                continue
            new_list.append(new_item)
        return new_list if changed else value
    return value


def _filter_cited_chunks(output: BaseModel, retrievals: Sequence[Retrieval]) -> BaseModel:
    """Drop any chunk_id the model emitted that isn't in the retrieval set,
    anywhere in the output tree (including inside nested NewsItem-style lists)."""
    existing = {r.chunk_id for r in retrievals}
    result = _walk_and_filter(output, existing)
    return result if isinstance(result, BaseModel) else output


async def run_agent(
    *,
    agent_name: str,
    prompt_name: str,
    output_schema: type[T],
    retrievals: Sequence[Retrieval],
    template_vars: dict[str, Any] | None = None,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 4096,
    thesis_id: UUID | None = None,
    job_id: UUID | None = None,
    llm_complete: LlmComplete | None = None,
    audit_log: AuditLog | None = None,
) -> T:
    """Run one agent end-to-end. Returns the validated output."""
    template_vars = dict(template_vars or {})
    template_vars.setdefault("context", format_retrievals(retrievals))

    user_msg = render_prompt(prompt_name, **template_vars)

    settings = get_settings()
    request = llm.LLMRequest(
        model=model or settings.anthropic_agent_model,
        system=system or DEFAULT_SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=max_tokens,
    )

    fn = llm_complete or llm.complete_structured
    audit_fn = audit_log or audit.log_event

    status: str = "ok"
    response: llm.LLMResponse | None = None
    output: T | None = None
    err: Exception | None = None
    try:
        output_raw, response = await fn(request, output_schema)
        output = _filter_cited_chunks(output_raw, retrievals)  # type: ignore[assignment]
    except Exception as exc:
        status = "error"
        err = exc
        log.exception("agent %s failed", agent_name)

    payload: dict[str, Any] = {
        "prompt_name": prompt_name,
        "retrieval_count": len(retrievals),
        "template_vars": {k: v for k, v in template_vars.items() if k != "context"},
    }
    if output is not None:
        payload["output"] = output.model_dump(mode="json")
    if response is not None and response.raw:
        # Persist what the model actually emitted, separately from the filtered
        # output, so post-processing (UUID filtering, item drops) is auditable.
        payload["output_raw"] = response.raw
    if err is not None:
        payload["error"] = repr(err)

    await audit_fn(
        actor=agent_name,
        action="agent_call",
        thesis_id=thesis_id,
        job_id=job_id,
        status=status,
        model=response.model if response else (model or settings.anthropic_agent_model),
        input_tokens=response.input_tokens if response else None,
        output_tokens=response.output_tokens if response else None,
        cost_usd=response.cost_usd if response else None,
        latency_ms=response.latency_ms if response else None,
        payload=payload,
    )

    if err is not None:
        raise err
    assert output is not None
    return output
