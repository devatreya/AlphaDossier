"""Generic IR-page fetcher.

Phase 2 only fetches; Phase 3 (chunker) will dispatch on content-type to extract
text. We return the raw body in `text` for HTML/text and leave PDF parsing to
the chunker — encoded as base64 in metadata if non-text.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

import httpx

from ._errors import ConnectorError
from ._http import make_client
from ._types import RawDocument

PROVIDER = "company_ir"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def fetch_url(
    url: str,
    *,
    title: str | None = None,
    client: httpx.AsyncClient | None = None,
    max_bytes: int = 10 * 1024 * 1024,
) -> RawDocument:
    """Fetch an IR URL and return a RawDocument.

    For HTML/text responses the body is placed in `text` verbatim. For binary
    responses (e.g. PDFs) `text` is empty and the bytes are base64-encoded under
    `metadata.body_b64` for the chunker to extract later. Aborts if the body
    exceeds max_bytes.
    """
    owned = client is None
    c = client or make_client()
    try:
        resp = await c.get(url)
    except httpx.RequestError as exc:
        if owned:
            await c.aclose()
        raise ConnectorError(f"company_ir: {exc}", provider=PROVIDER) from exc

    if owned:
        await c.aclose()

    if resp.status_code >= 400:
        raise ConnectorError(
            f"company_ir {resp.status_code}: {url}", provider=PROVIDER
        )

    body = resp.content
    if len(body) > max_bytes:
        raise ConnectorError(
            f"company_ir: response too large ({len(body)} > {max_bytes}) for {url}",
            provider=PROVIDER,
        )

    content_type = (resp.headers.get("content-type") or "").lower()
    is_text = "text/" in content_type or "html" in content_type or "xml" in content_type

    metadata: dict = {
        "content_type": content_type,
        "byte_length": len(body),
    }
    text_body = ""
    if is_text:
        try:
            text_body = body.decode(resp.charset_encoding or "utf-8", errors="replace")
        except (LookupError, UnicodeDecodeError):
            text_body = body.decode("utf-8", errors="replace")
    else:
        metadata["body_b64"] = base64.b64encode(body).decode("ascii")

    return RawDocument(
        kind="ir_html" if is_text else "ir_binary",
        provider=PROVIDER,
        url=url,
        title=title,
        published_at=datetime.now(tz=timezone.utc),
        text=text_body,
        content_hash=_sha256(body),
        metadata=metadata,
    )
