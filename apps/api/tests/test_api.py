"""API/e2e tests for health + /me (no DB).

JWKS prefetch in the app lifespan is patched to a no-op so tests don't hit the
network. The happy-path /me test overrides the auth dependency; the unauthorized
path exercises the real bearer-scheme rejection.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    # Avoid network during lifespan JWKS prefetch.
    from app.core import auth as auth_mod

    async def _noop():
        return None

    monkeypatch.setattr(auth_mod.jwks_cache, "_refresh", _noop)

    from app.main import app

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


def test_me_requires_auth(client):
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401


def test_me_happy(client):
    from app.core.auth import Principal, get_current_principal
    from app.main import app

    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id="auth0|652f",
        tenant_id="0e3f9c2a-1c44-4f6e-9b21-2a5d8e7f1234",
        role="cfo",
        entity_id="8a1b0000-0000-0000-0000-000000000000",
        email="cfo@acme.com",
        permissions=("dashboard:read", "nirvana:use"),
    )
    resp = client.get("/api/v1/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "0e3f9c2a-1c44-4f6e-9b21-2a5d8e7f1234"
    assert body["role"] == "cfo"
    assert "dashboard:read" in body["permissions"]


def test_openapi_served(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "Terzo Cost Intelligence API"
