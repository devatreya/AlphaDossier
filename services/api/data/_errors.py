"""Connector exceptions. Phase 4 orchestrator catches these and logs to audit."""
from __future__ import annotations


class ConnectorError(Exception):
    """Base for any data-connector failure (network, parse, upstream 5xx)."""

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider


class MissingApiKeyError(ConnectorError):
    """Raised when a required API key is not configured.

    Connectors raise this rather than returning empty results so the orchestrator
    can decide whether to mark the agent unavailable or proceed without it.
    """

    def __init__(self, env_var: str, *, provider: str) -> None:
        super().__init__(
            f"Missing required env var {env_var!r} for provider {provider!r}.",
            provider=provider,
        )
        self.env_var = env_var
