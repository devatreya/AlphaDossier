from __future__ import annotations

from uuid import uuid4

import pytest

from services.api.ingest import citations

from .conftest import FakeConn


def test_validate_citation_full_overlap() -> None:
    claim = "Revenue grew 12% year-on-year to $45 billion."
    chunks = ["Acme reported revenue of $45 billion, growing 12% year-on-year."]
    result = citations.validate_citation(claim, chunks)
    assert result.ok
    assert result.overlap_score >= 0.8


def test_validate_citation_zero_overlap() -> None:
    claim = "The CFO resigned in March."
    chunks = ["Battery technology improvements drove margin expansion."]
    result = citations.validate_citation(claim, chunks)
    assert not result.ok
    assert result.overlap_score == 0.0


def test_validate_citation_partial_below_threshold() -> None:
    claim = "Cash reserves fell from $20 billion to $14 billion in Q3."
    chunks = ["Cash reserves fell to $14 billion."]
    result = citations.validate_citation(claim, chunks, min_overlap=0.95)
    assert not result.ok
    assert "$20" in result.missing_terms or "20" in result.missing_terms


def test_validate_citation_partial_above_threshold() -> None:
    claim = "Cash reserves fell to $14 billion."
    chunks = ["The company reported cash reserves of $14 billion at quarter end."]
    result = citations.validate_citation(claim, chunks, min_overlap=0.5)
    assert result.ok
    assert "14" in [t.strip(".,") for t in result.matched_terms] or "$14" in result.matched_terms


def test_validate_citation_no_chunks() -> None:
    result = citations.validate_citation("Anything goes here.", [])
    assert not result.ok
    assert "no supporting chunks" in (result.reason or "")


def test_validate_citation_empty_claim() -> None:
    result = citations.validate_citation("", ["any text"])
    assert not result.ok
    assert "no extractable" in (result.reason or "")


def test_extract_terms_drops_stopwords() -> None:
    terms = citations._extract_terms("The CFO of Acme resigned in March of 2026.")
    assert "the" not in terms
    assert "of" not in terms
    assert "in" not in terms
    assert "cfo" in terms
    assert "acme" in terms
    assert "resigned" in terms
    assert "march" in terms
    assert "2026" in terms


async def test_insert_citation_rejects_empty_chunk_ids() -> None:
    """A citation with no supporting chunks violates the repo rule that every
    important claim must cite source chunks. The store must refuse it outright."""
    conn = FakeConn()
    with pytest.raises(ValueError, match="at least one chunk_id"):
        await citations.insert_citation(
            uuid4(), "bull_case", "Acme is great", [], conn=conn,
        )
    # Confirm we never reached the DB.
    assert conn.calls == []


async def test_insert_citation_persists_when_supported() -> None:
    conn = FakeConn()
    new_id = uuid4()
    conn.fetchval_results = [new_id]

    thesis_id = uuid4()
    chunk_ids = [uuid4(), uuid4()]
    out = await citations.insert_citation(
        thesis_id, "catalysts", "Q4 product launch", chunk_ids,
        confidence=0.7, conn=conn,
    )
    assert out == new_id
    method, sql, args = next(
        c for c in conn.calls if c[0] == "fetchval" and "insert into citations" in c[1]
    )
    assert args[0] == thesis_id
    assert args[1] == "catalysts"
    assert args[3] == chunk_ids
    assert args[4] == 0.7


def test_extract_terms_keeps_numbers_and_percentages() -> None:
    terms = citations._extract_terms("Margin rose from 18.5% to 22% in Q3.")
    # The regex captures numerics including the percent sign attachment.
    has_percent = any("18.5" in t or "22" in t for t in terms)
    assert has_percent
