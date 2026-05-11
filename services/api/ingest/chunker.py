"""Document chunker.

Takes a `RawDocument` from the data connectors and produces text chunks
ready for embedding. Dispatches on the document kind / content-type:

  * HTML  → BeautifulSoup strip → plain text
  * PDF   → pypdf extract → plain text  (binary body lives in metadata.body_b64)
  * other → use doc.text as-is

The splitter is paragraph-aware: it greedily packs paragraphs into chunks up
to a target character size, then emits an overlap suffix into the next chunk
so retrieval queries that fall on a chunk boundary still match.
"""
from __future__ import annotations

import base64
import logging
import re
from io import BytesIO

from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ..data._types import RawDocument
from ._types import Chunk

log = logging.getLogger(__name__)

DEFAULT_TARGET_CHARS = 1500
DEFAULT_OVERLAP_CHARS = 200
MIN_CHUNK_CHARS = 30
"""Drop chunks shorter than this — usually leftover boilerplate or empty splits.
Set low so legitimately short documents (news snippets, short RNS items) pass."""

# Voyage-finance-2 max tokens per input is large; this estimate just informs
# token_count for rough budgeting. ~4 chars per token is the standard heuristic.
_CHARS_PER_TOKEN = 4

# Tags whose text content is rarely useful for analysis.
_SKIP_TAGS = {"script", "style", "noscript", "head", "meta", "link"}

_WHITESPACE_RUN = re.compile(r"[ \t ]+")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
# After HTML extraction, BeautifulSoup's get_text(separator=" ") leaves stray
# spaces before sentence-final punctuation when an inline tag closes mid-sentence
# (`<b>foo</b>.` -> `foo .`). Tighten that up.
_SPACE_BEFORE_PUNCT = re.compile(r" +([.,;:!?](?:\s|$))")


def _approx_token_count(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _normalise_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs but preserve paragraph breaks."""
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    lines = [_WHITESPACE_RUN.sub(" ", line).strip() for line in text.splitlines()]
    out: list[str] = []
    blank_streak = 0
    for line in lines:
        if not line:
            blank_streak += 1
            if blank_streak == 1:
                out.append("")
        else:
            blank_streak = 0
            out.append(line)
    return "\n".join(out).strip()


# Block-level HTML elements that should produce a paragraph break in the
# extracted text. Inline elements (span, b, i, a, em, strong, etc.) stay inline.
_BLOCK_TAGS = frozenset(
    {
        "p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "ul", "ol", "tr", "table", "blockquote",
        "section", "article", "header", "footer", "hr", "pre", "address",
    }
)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(list(_SKIP_TAGS)):
        tag.decompose()
    # Append a newline after each block-level element so paragraph structure
    # is preserved while inline elements (b, i, span, ...) stay on one line.
    for tag in soup.find_all(list(_BLOCK_TAGS)):
        tag.append("\n\n")
    text = soup.get_text(separator=" ")
    return _normalise_whitespace(text)


def pdf_to_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, ValueError, OSError) as exc:
        log.warning("PDF parse failed (%s) — returning empty text", exc)
        return ""
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # pypdf can raise a wide variety here
            log.warning("PDF page %d extraction failed", i, exc_info=True)
    return _normalise_whitespace("\n\n".join(parts))


def extract_text(doc: RawDocument) -> str:
    """Return chunkable plain text for a RawDocument, dispatching on kind."""
    content_type = (doc.metadata.get("content_type") or "").lower()

    if doc.kind == "ir_binary" or "pdf" in content_type:
        b64 = doc.metadata.get("body_b64")
        if not b64:
            return ""
        try:
            return pdf_to_text(base64.b64decode(b64))
        except (ValueError, TypeError) as exc:
            log.warning("PDF base64 decode failed: %s", exc)
            return ""

    if doc.kind == "ir_html" or "html" in content_type or "xml" in content_type:
        return html_to_text(doc.text)

    return _normalise_whitespace(doc.text)


def _split_into_paragraphs(text: str) -> list[str]:
    paras = [p.strip() for p in _PARAGRAPH_SPLIT.split(text)]
    return [p for p in paras if p]


def _split_long_paragraph(paragraph: str, target_chars: int) -> list[str]:
    """If a single paragraph exceeds target_chars, hard-split on sentence
    boundaries (then on character count if still too long)."""
    if len(paragraph) <= target_chars:
        return [paragraph]
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    out: list[str] = []
    cur = ""
    for s in sentences:
        if not cur:
            cur = s
        elif len(cur) + 1 + len(s) <= target_chars:
            cur = f"{cur} {s}"
        else:
            out.append(cur)
            cur = s
    if cur:
        out.append(cur)
    # Final fallback: if any sentence is still huge, hard cut.
    final: list[str] = []
    for piece in out:
        while len(piece) > target_chars:
            final.append(piece[:target_chars])
            piece = piece[target_chars:]
        final.append(piece)
    return final


def _pack_chunks(
    paragraphs: list[str], *, target_chars: int, overlap_chars: int
) -> list[str]:
    """Greedy paragraph packing with character-level overlap between chunks."""
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_len = 0
    for para in paragraphs:
        for piece in _split_long_paragraph(para, target_chars):
            piece_len = len(piece) + (2 if buffer else 0)  # +2 for "\n\n"
            if buffer and buffer_len + piece_len > target_chars:
                chunks.append("\n\n".join(buffer))
                if overlap_chars > 0:
                    tail = chunks[-1][-overlap_chars:]
                    buffer = [tail, piece]
                    buffer_len = len(tail) + 2 + len(piece)
                else:
                    buffer = [piece]
                    buffer_len = len(piece)
            else:
                buffer.append(piece)
                buffer_len += piece_len
    if buffer:
        chunks.append("\n\n".join(buffer))
    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]


def chunk_document(
    doc: RawDocument,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[Chunk]:
    """Chunk a single RawDocument. Returns [] for empty/unsupported documents."""
    if target_chars <= 0:
        raise ValueError("target_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= target_chars:
        raise ValueError("overlap_chars must be in [0, target_chars)")

    text = extract_text(doc)
    if not text.strip():
        return []

    paragraphs = _split_into_paragraphs(text)
    if not paragraphs:
        return []

    pieces = _pack_chunks(
        paragraphs, target_chars=target_chars, overlap_chars=overlap_chars
    )
    base_metadata = {
        "source_kind": doc.kind,
        "source_provider": doc.provider,
        "source_url": doc.url,
        "source_title": doc.title,
    }
    return [
        Chunk(
            text=piece,
            chunk_index=i,
            token_count=_approx_token_count(piece),
            metadata=dict(base_metadata),
        )
        for i, piece in enumerate(pieces)
    ]
