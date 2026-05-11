"""Shared httpx helpers: client factory + retry wrapper.

Connectors accept an optional `client` arg so tests can inject `httpx.MockTransport`.
When no client is provided, callers should `async with make_client()` themselves.

Retry policy: transport errors, 5xx, and 429 are retried up to `retries` extra
times. 429 honours the `Retry-After` header (capped at MAX_RETRY_AFTER seconds).
4xx other than 429 raise immediately.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping

import httpx

from ._errors import ConnectorError

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DEFAULT_USER_AGENT = "AI-quant/0.1 (research prototype; contact: noreply@example.com)"

# Cap Retry-After so a misbehaving upstream cannot stall request handlers.
MAX_RETRY_AFTER = 60.0


def make_client(
    *,
    headers: Mapping[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    base_url: str | None = None,
) -> httpx.AsyncClient:
    merged: dict[str, str] = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged.update(dict(headers))
    return httpx.AsyncClient(
        headers=merged,
        timeout=timeout or DEFAULT_TIMEOUT,
        transport=transport,
        follow_redirects=True,
        base_url=base_url or "",
    )


def _is_retryable_status(status: int) -> bool:
    return status == 429 or 500 <= status < 600


def _retry_delay(
    response: httpx.Response | None,
    *,
    attempt: int,
    backoff: float,
) -> float:
    """Compute sleep before the next retry.

    Honours `Retry-After` (seconds form only — HTTP-date is uncommon for APIs)
    capped at MAX_RETRY_AFTER. Falls back to exponential backoff.
    """
    if response is not None:
        ra = response.headers.get("Retry-After")
        if ra:
            try:
                return min(float(ra), MAX_RETRY_AFTER)
            except ValueError:
                pass
    return backoff * (2**attempt)


async def _perform(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None,
    headers: Mapping[str, str] | None,
    json_body: Any | None,
    retries: int,
    backoff: float,
    provider: str,
) -> httpx.Response:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.request(
                method, url, params=params, headers=headers, json=json_body
            )
        except httpx.RequestError as exc:
            last_err = exc
            log.warning("%s transport error attempt %d: %s", provider, attempt + 1, exc)
            if attempt == retries:
                raise ConnectorError(
                    f"{provider}: transport error: {exc}", provider=provider
                ) from exc
            await asyncio.sleep(_retry_delay(None, attempt=attempt, backoff=backoff))
            continue

        if _is_retryable_status(resp.status_code):
            last_err = ConnectorError(
                f"{provider} {resp.status_code} from {url}", provider=provider
            )
            log.warning(
                "%s retryable status attempt %d: %s",
                provider, attempt + 1, resp.status_code,
            )
            if attempt == retries:
                raise last_err
            await asyncio.sleep(_retry_delay(resp, attempt=attempt, backoff=backoff))
            continue

        if resp.status_code >= 400:
            raise ConnectorError(
                f"{provider} {resp.status_code}: {resp.text[:200]}", provider=provider
            )

        return resp

    raise last_err or ConnectorError(f"{provider}: exhausted retries", provider=provider)


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    json_body: Any | None = None,
    retries: int = 2,
    backoff: float = 0.5,
    provider: str = "unknown",
) -> Any:
    resp = await _perform(
        client, method, url,
        params=params, headers=headers, json_body=json_body,
        retries=retries, backoff=backoff, provider=provider,
    )
    try:
        return resp.json()
    except ValueError as exc:
        raise ConnectorError(
            f"{provider}: non-JSON response from {url}", provider=provider
        ) from exc


async def request_text(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    retries: int = 2,
    backoff: float = 0.5,
    provider: str = "unknown",
) -> str:
    resp = await _perform(
        client, method, url,
        params=params, headers=headers, json_body=None,
        retries=retries, backoff=backoff, provider=provider,
    )
    return resp.text
