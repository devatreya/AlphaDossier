from __future__ import annotations

import base64
from datetime import datetime, timezone

from services.api.data._types import RawDocument
from services.api.ingest import chunker


def _doc(text: str = "", *, kind: str = "news", **metadata) -> RawDocument:
    return RawDocument(
        kind=kind,
        provider="test",
        url="https://example/x",
        title="Example",
        published_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
        text=text,
        metadata=metadata,
    )


def test_html_to_text_strips_tags_and_scripts() -> None:
    html = """
    <html><head><title>X</title><script>alert(1)</script></head>
    <body><h1>Hello</h1><p>World <b>foo</b>.</p>
    <style>.a{}</style>
    </body></html>
    """
    out = chunker.html_to_text(html)
    assert "Hello" in out
    assert "World foo." in out
    assert "alert" not in out
    assert ".a{}" not in out


def test_pdf_to_text_returns_empty_on_garbage() -> None:
    assert chunker.pdf_to_text(b"not a pdf") == ""


def test_chunk_short_text_emits_single_chunk() -> None:
    doc = _doc("Short news item describing Acme's strong Q3.", kind="news")
    chunks = chunker.chunk_document(doc, target_chars=1500, overlap_chars=200)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert "Acme" in chunks[0].text
    assert chunks[0].metadata["source_kind"] == "news"
    assert chunks[0].token_count > 0


def test_chunk_long_text_packs_with_overlap() -> None:
    paragraphs = [f"Paragraph {i}: " + ("lorem ipsum dolor sit amet " * 20) for i in range(8)]
    doc = _doc("\n\n".join(paragraphs), kind="ir_html")
    # Need to bypass html parsing for plain text — set kind to a non-html kind.
    doc = _doc("\n\n".join(paragraphs), kind="news")
    chunks = chunker.chunk_document(doc, target_chars=600, overlap_chars=80)
    assert len(chunks) >= 2
    # Indices monotonic and zero-based.
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # Each chunk respects (roughly) the target size.
    assert all(len(c.text) <= 600 + 100 for c in chunks)
    # Overlap: last 80 chars of chunk N appear at start of chunk N+1.
    for i in range(len(chunks) - 1):
        tail = chunks[i].text[-80:]
        assert tail in chunks[i + 1].text


def test_chunk_html_document() -> None:
    html = "<html><body><p>" + ("Buy bonds. " * 200) + "</p></body></html>"
    doc = RawDocument(
        kind="ir_html",
        provider="company_ir",
        text=html,
        metadata={"content_type": "text/html"},
    )
    chunks = chunker.chunk_document(doc, target_chars=500, overlap_chars=50)
    assert chunks
    assert "<p>" not in chunks[0].text
    assert "Buy bonds" in chunks[0].text


def test_chunk_pdf_via_metadata_body() -> None:
    """When extract returns nothing (garbage PDF), no chunks are produced."""
    doc = RawDocument(
        kind="ir_binary",
        provider="company_ir",
        text="",
        metadata={
            "content_type": "application/pdf",
            "body_b64": base64.b64encode(b"not a real pdf").decode("ascii"),
        },
    )
    assert chunker.chunk_document(doc) == []


def test_chunk_empty_document_returns_empty() -> None:
    doc = _doc("", kind="news")
    assert chunker.chunk_document(doc) == []


def test_invalid_target_chars_raises() -> None:
    import pytest

    doc = _doc("hello world")
    with pytest.raises(ValueError):
        chunker.chunk_document(doc, target_chars=0)
    with pytest.raises(ValueError):
        chunker.chunk_document(doc, target_chars=100, overlap_chars=100)


def test_huge_paragraph_is_split_on_sentences() -> None:
    sentences = [f"Sentence number {i} runs on for several words." for i in range(60)]
    doc = _doc(" ".join(sentences), kind="news")
    chunks = chunker.chunk_document(doc, target_chars=300, overlap_chars=40)
    assert len(chunks) >= 2
    # Sentence boundaries preferred — chunks should rarely cut mid-word.
    for c in chunks:
        assert not c.text.endswith(" ")
