from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.main import app


def test_healthz_is_liveness_only() -> None:
    with TestClient(app) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok"}


def test_readyz_returns_503_without_db() -> None:
    """Tests run without DATABASE_URL, so init_pool should yield no pool and
    /readyz must report unavailable + 503."""
    with TestClient(app) as client:
        resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "unavailable"
    assert "providers" in body
    assert set(body["providers"].keys()) == {
        "anthropic",
        "voyage",
        "news_api",
        "fred",
        "supabase",
    }


def test_root() -> None:
    with TestClient(app) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "AI-quant API"
    assert body["liveness"] == "/healthz"
    assert body["readiness"] == "/readyz"
