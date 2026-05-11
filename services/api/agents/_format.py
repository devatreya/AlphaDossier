"""Format `Retrieval` objects into prompt context with stable citation tags.

The format is deliberately simple and easy for the model to cite back: each
chunk is preceded by a header that names a citation tag (`C1`, `C2`, ...) and
its UUID. The agent's output schema includes `cited_chunk_ids` as UUIDs, which
makes downstream validation in `_base.py` straightforward.
"""
from __future__ import annotations

from typing import Iterable
from uuid import UUID

from ..ingest._types import Retrieval


def _header(tag: str, retrieval: Retrieval) -> str:
    parts = [f"[{tag}]"]
    if retrieval.source_kind:
        parts.append(f"kind={retrieval.source_kind}")
    if retrieval.source_provider:
        parts.append(f"provider={retrieval.source_provider}")
    if retrieval.source_title:
        parts.append(f'title="{retrieval.source_title}"')
    if retrieval.source_url:
        parts.append(f"url={retrieval.source_url}")
    parts.append(f"chunk_id={retrieval.chunk_id}")
    parts.append(f"sim={retrieval.similarity:.3f}")
    return " ".join(parts)


def format_retrievals(retrievals: Iterable[Retrieval]) -> str:
    """Render an iterable of retrievals as a numbered, attributed context block.

    Returns "(no relevant context)" when the iterable is empty so the prompt
    stays well-formed instead of having a dangling section.
    """
    blocks: list[str] = []
    for i, r in enumerate(retrievals, start=1):
        tag = f"C{i}"
        blocks.append(f"{_header(tag, r)}\n{r.text}".rstrip())
    if not blocks:
        return "(no relevant context retrieved)"
    return "\n\n---\n\n".join(blocks)


def existing_chunk_ids(retrievals: Iterable[Retrieval]) -> set[UUID]:
    return {r.chunk_id for r in retrievals}


def filter_to_existing(
    cited: Iterable[UUID], retrievals: Iterable[Retrieval]
) -> list[UUID]:
    """Drop any chunk_id the model emitted that isn't in the retrieval set.

    Anthropic models very rarely hallucinate UUIDs, but we treat this as a
    hard contract — anything we couldn't verify against the retrieved chunks
    is dropped before reaching the citations table.
    """
    existing = existing_chunk_ids(retrievals)
    seen: set[UUID] = set()
    out: list[UUID] = []
    for cid in cited:
        if cid in existing and cid not in seen:
            out.append(cid)
            seen.add(cid)
    return out
