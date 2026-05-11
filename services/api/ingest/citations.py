"""Citation persistence + heuristic validation.

A citation links a claim made in the synthesised thesis to the chunks that
support it. Phase 4 agents emit `(section, claim, chunk_ids)` tuples; this
module persists them and runs a cheap sanity check.

`validate_citation` is intentionally a heuristic — its purpose is to catch
obvious hallucinations (a claim mentioning numbers/entities that appear
nowhere in the cited chunks). It is advisory: callers can choose to drop the
citation, downgrade confidence, or flag the synthesizer for retry.
"""
from __future__ import annotations

import json
import re
from typing import Sequence
from uuid import UUID

import asyncpg

from ..db import acquire
from ._types import CitationValidation

_INSERT_CITATION_SQL = """
    insert into citations (thesis_id, section, claim, chunk_ids, confidence)
    values ($1, $2, $3, $4, $5)
    returning id
"""

_GET_CITATION_SQL = """
    select id, thesis_id, section, claim, chunk_ids, confidence, created_at
    from citations
    where id = $1
"""

# Common stop-words that add noise to overlap scoring without carrying meaning.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "of", "in", "to", "for", "on", "at", "by", "with",
        "and", "or", "but", "if", "then", "than", "as", "is", "are", "was",
        "were", "be", "been", "being", "this", "that", "these", "those",
        "it", "its", "they", "them", "their", "we", "our", "you", "your",
        "he", "she", "his", "her", "from", "into", "about", "over", "under",
        "more", "most", "less", "least", "such", "some", "any", "all", "no",
        "not", "do", "does", "did", "have", "has", "had", "will", "would",
        "should", "could", "may", "might", "can", "shall", "also", "very",
        "much", "many", "much", "while", "during", "between", "across",
    }
)

# Words containing letters or digits, including in-word periods (10.5%) and
# hyphens (year-on-year). We keep numbers because they are exactly the kind of
# claim we want to verify against the source.
_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9.\-]*[A-Za-z0-9]|\d[\d.,%\-]*")


def _extract_terms(text: str) -> set[str]:
    """Lowercased content terms — letters/digits with stopwords removed."""
    raw = _TERM_RE.findall(text or "")
    out: set[str] = set()
    for tok in raw:
        # Strip trailing punctuation that the regex permitted in-word.
        tok = tok.strip(".,-")
        if not tok:
            continue
        lowered = tok.lower()
        if lowered in _STOPWORDS:
            continue
        if len(lowered) <= 1 and not lowered.isdigit():
            continue
        out.add(lowered)
    return out


def validate_citation(
    claim: str,
    supporting_texts: Sequence[str],
    *,
    min_overlap: float = 0.2,
) -> CitationValidation:
    """Heuristic check: does the claim's content vocabulary appear in the cited chunks?

    Returns ok=True if the fraction of claim terms found in the union of
    supporting chunk terms meets `min_overlap`. Tunable per agent.
    """
    claim_terms = _extract_terms(claim)
    if not claim_terms:
        return CitationValidation(
            ok=False,
            overlap_score=0.0,
            reason="claim has no extractable content terms",
        )

    if not supporting_texts:
        return CitationValidation(
            ok=False,
            overlap_score=0.0,
            missing_terms=sorted(claim_terms),
            reason="no supporting chunks provided",
        )

    chunk_terms: set[str] = set()
    for t in supporting_texts:
        chunk_terms |= _extract_terms(t)

    matched = sorted(claim_terms & chunk_terms)
    missing = sorted(claim_terms - chunk_terms)
    score = len(matched) / len(claim_terms)
    return CitationValidation(
        ok=score >= min_overlap,
        overlap_score=round(score, 4),
        matched_terms=matched,
        missing_terms=missing,
        reason=None if score >= min_overlap else f"overlap {score:.0%} below {min_overlap:.0%}",
    )


async def insert_citation(
    thesis_id: UUID,
    section: str,
    claim: str,
    chunk_ids: Sequence[UUID],
    *,
    confidence: float | None = None,
    conn: asyncpg.Connection | None = None,
) -> UUID:
    """Persist a citation. Empty chunk_ids is rejected: per the repo rule,
    every important claim must cite at least one source chunk. Callers should
    drop or fix the claim before reaching this point — typically by calling
    `validate_citation` first."""
    if not chunk_ids:
        raise ValueError(
            "citations must reference at least one chunk_id; "
            "validate or drop the claim before inserting"
        )
    args = (thesis_id, section, claim, list(chunk_ids), confidence)
    if conn is not None:
        return await conn.fetchval(_INSERT_CITATION_SQL, *args)
    async with acquire() as c:
        return await c.fetchval(_INSERT_CITATION_SQL, *args)


async def get_citation(
    citation_id: UUID, *, conn: asyncpg.Connection | None = None
) -> dict | None:
    if conn is not None:
        row = await conn.fetchrow(_GET_CITATION_SQL, citation_id)
    else:
        async with acquire() as c:
            row = await c.fetchrow(_GET_CITATION_SQL, citation_id)
    if row is None:
        return None
    out = dict(row)
    # Normalise jsonb-as-string if codec wasn't applied.
    for k, v in list(out.items()):
        if isinstance(v, str) and k in {"metadata"}:
            try:
                out[k] = json.loads(v)
            except ValueError:
                pass
    return out
