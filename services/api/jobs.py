"""Background job dispatch.

For Phase 5 we run the orchestrator inside the FastAPI process via
`asyncio.create_task`. That's enough for a prototype: status transitions are
written to the `theses` row by the orchestrator itself, so the frontend can
poll `GET /thesis/{id}` to see progress.

Long-term, swap `run_thesis_in_background` for a queue-backed worker (arq /
celery / temporal). The route layer goes through `get_thesis_dispatcher` so
that swap is one dependency override away.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from .orchestrator import ThesisOrchestrator, ThesisRunRequest

log = logging.getLogger(__name__)


async def run_thesis_in_background(request: ThesisRunRequest) -> None:
    """Top-level coroutine for `asyncio.create_task`.

    Catches and logs failures: the route handler has already returned by the
    time this runs, so an unhandled exception would only surface in stderr.
    The orchestrator updates the theses row to `status='failed'` on its own
    error path, so frontend pollers still see the failure.
    """
    try:
        await ThesisOrchestrator().run(request)
    except Exception:
        log.exception(
            "Background thesis run failed (thesis_id=%s, ticker=%s)",
            request.thesis_id, request.ticker,
        )


def get_thesis_dispatcher() -> Callable[[ThesisRunRequest], Awaitable[None]]:
    """FastAPI dependency. Tests override via `app.dependency_overrides`."""
    return run_thesis_in_background
