from __future__ import annotations

import httpx
import pytest

from services.api.data import company_ir
from services.api.data._errors import ConnectorError

from .conftest import make_mock_client


async def test_fetch_html() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html><body>Annual report</body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    async with make_mock_client(handler) as client:
        doc = await company_ir.fetch_url(
            "https://acme.example/ir/2026",
            title="Acme Annual Report",
            client=client,
        )

    assert doc.kind == "ir_html"
    assert "Annual report" in doc.text
    assert doc.title == "Acme Annual Report"
    assert doc.content_hash is not None


async def test_fetch_pdf_encodes_body() -> None:
    pdf_bytes = b"%PDF-1.4\n...\n%%EOF"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=pdf_bytes,
            headers={"content-type": "application/pdf"},
        )

    async with make_mock_client(handler) as client:
        doc = await company_ir.fetch_url("https://acme.example/q1.pdf", client=client)

    assert doc.kind == "ir_binary"
    assert doc.text == ""
    assert "body_b64" in doc.metadata
    assert doc.metadata["content_type"] == "application/pdf"


async def test_fetch_too_large_aborts() -> None:
    big = b"x" * 1024

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big, headers={"content-type": "text/plain"})

    async with make_mock_client(handler) as client:
        with pytest.raises(ConnectorError, match="too large"):
            await company_ir.fetch_url(
                "https://acme.example/big", client=client, max_bytes=512
            )


async def test_fetch_4xx_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    async with make_mock_client(handler) as client:
        with pytest.raises(ConnectorError):
            await company_ir.fetch_url("https://acme.example/missing", client=client)
