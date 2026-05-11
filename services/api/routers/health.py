from __future__ import annotations

from fastapi import APIRouter, Response

from ..config import get_settings
from ..db import ping

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness probe. Returns 200 as long as the process is running.

    Does *not* check downstream dependencies — use /readyz for that.
    """
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(response: Response) -> dict:
    """Readiness probe. 200 when DB is reachable, 503 otherwise.

    Reports per-provider key presence so the frontend can show what's wired up.
    Key presence != provider reachability — those checks land in later phases.
    """
    settings = get_settings()
    db_ok = await ping()
    if not db_ok:
        response.status_code = 503
    return {
        "status": "ok" if db_ok else "degraded",
        "env": settings.app_env,
        "db": "ok" if db_ok else "unavailable",
        "providers": {
            "anthropic": bool(settings.anthropic_api_key),
            "voyage": bool(settings.voyage_api_key),
            "news_api": bool(settings.news_api_key),
            "fred": bool(settings.fred_api_key),
            "supabase": bool(settings.supabase_url and settings.supabase_anon_key),
        },
    }


@router.get("/")
async def root() -> dict:
    return {
        "name": "AI-quant API",
        "docs": "/docs",
        "liveness": "/healthz",
        "readiness": "/readyz",
    }
