from __future__ import annotations

from uuid import uuid4

from services.api.agents import _format
from services.api.ingest._types import Retrieval


def _r(text: str = "lorem", *, kind: str | None = "news", title: str | None = "T") -> Retrieval:
    return Retrieval(
        chunk_id=uuid4(),
        source_id=uuid4(),
        text=text,
        chunk_index=0,
        similarity=0.9,
        source_kind=kind,
        source_provider="news_api",
        source_url="https://x",
        source_title=title,
        metadata={},
    )


def test_format_retrievals_emits_citation_tags() -> None:
    rs = [_r("first chunk text"), _r("second chunk")]
    out = _format.format_retrievals(rs)
    assert "[C1]" in out
    assert "[C2]" in out
    assert "first chunk text" in out
    assert "second chunk" in out
    assert "chunk_id=" in out
    # Header should record source_kind and similarity.
    assert "kind=news" in out
    assert "sim=0.900" in out


def test_format_retrievals_empty_returns_placeholder() -> None:
    assert _format.format_retrievals([]) == "(no relevant context retrieved)"


def test_filter_to_existing_drops_unknown_and_dedupes() -> None:
    rs = [_r(), _r()]
    valid = [r.chunk_id for r in rs]
    extra = uuid4()
    filtered = _format.filter_to_existing([valid[0], extra, valid[1], valid[0]], rs)
    assert filtered == [valid[0], valid[1]]
