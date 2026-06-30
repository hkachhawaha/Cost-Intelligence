"""Phase 10 integration (§6, §8, §16) — live Postgres, migration 010.

The Commitment Check API (advisory verdict persisted immutably; sign-off once → 409; role
gate), multi-entity portfolio governance (vendor leverage across entities; RBAC), and the
degradation endpoint. No LLM key needed (rationale degrades to a deterministic summary).

Run: RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_commitment_pipeline.py -v
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requires_db

pytestmark = requires_db

_TRUNCATE = (
    "TRUNCATE tenants, users, entities, vendors, contracts, spend_records, opportunities, "
    "commitment_checks, portfolio_rollups, tenant_quotas, spend_tier_metadata, "
    "agent_runs, audit_events CASCADE"
)


def _dsn() -> str:
    from app.core.config import settings

    return settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")


def _admin():
    import psycopg

    return psycopg.connect(_dsn(), autocommit=True)


@pytest.fixture()
def tenant():
    tid = str(uuid.uuid4())
    yield tid
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(_TRUNCATE)
    admin.close()


def _client(tenant: str, user_id: str, role: str, monkeypatch) -> TestClient:
    from app.core import auth as auth_mod
    from app.core.auth import Principal, get_current_principal
    from app.core.database import get_session, session_for_tenant
    from app.main import app

    async def _noop():
        return None

    monkeypatch.setattr(auth_mod.jwks_cache, "_refresh", _noop)

    async def _principal() -> Principal:
        return Principal(
            user_id=user_id, tenant_id=tenant, role=role, entity_id=None,
            email="u@acme.com", permissions=("*",),
        )

    async def _session():
        s = await session_for_tenant(tenant)
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise
        finally:
            await s.close()

    app.dependency_overrides[get_current_principal] = _principal
    app.dependency_overrides[get_session] = _session
    return TestClient(app)


async def _seed_user(tenant: str, user_id: str) -> None:
    from app.core.database import session_for_tenant
    from app.models.tenant import Tenant
    from app.models.user import User

    tid = uuid.UUID(tenant)
    async with await session_for_tenant(tenant) as s:
        s.add(Tenant(id=tid, name="Acme", slug=f"acme{tenant[:8]}", encryption_key_ref="kms://t"))
        await s.flush()
        s.add(User(id=uuid.UUID(user_id), tenant_id=tid, auth0_id=f"a|{user_id[:8]}",
                   email="cfo@acme.com"))
        await s.commit()


_DEAL = {"vendor_name": "CloudCo", "acv": "1200000.00", "term_months": 36,
         "indexed_share": "0.60", "assumed_index_pct": "0.03", "margin_tolerance": "800000.00"}


# ── positive: run check → block verdict persisted + audited ───────────────────────
def test_commitment_check_block_and_audit(tenant, monkeypatch):
    user_id = str(uuid.uuid4())
    asyncio.run(_seed_user(tenant, user_id))
    client = _client(tenant, user_id, "cfo", monkeypatch)
    try:
        r = client.post("/api/v1/commitment-check", json=_DEAL)
        assert r.status_code == 200
        body = r.json()
        assert body["indexed_exposure"] == "741600.00"
        assert body["verdict"] == "block"  # 10% breaches 800k tolerance
        assert body["advisory"] is True
        assert len(body["scenarios"]) == 3

        admin = _admin()
        with admin.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM audit_events WHERE tenant_id=%s AND event_type=%s",
                (tenant, "commitment.checked"),
            )
            assert cur.fetchone()[0] == 1
        admin.close()
    finally:
        from app.main import app

        app.dependency_overrides.clear()


# ── validation: indexed_share out of [0,1] → 422 ─────────────────────────────────
def test_commitment_check_invalid_share_422(tenant, monkeypatch):
    user_id = str(uuid.uuid4())
    asyncio.run(_seed_user(tenant, user_id))
    client = _client(tenant, user_id, "cfo", monkeypatch)
    try:
        bad = {**_DEAL, "indexed_share": "1.5"}
        assert client.post("/api/v1/commitment-check", json=bad).status_code == 422
    finally:
        from app.main import app

        app.dependency_overrides.clear()


# ── error: a check can be signed once; a second sign → 409 ────────────────────────
def test_commitment_sign_once_then_409(tenant, monkeypatch):
    user_id = str(uuid.uuid4())
    asyncio.run(_seed_user(tenant, user_id))
    client = _client(tenant, user_id, "cfo", monkeypatch)
    try:
        cid = client.post("/api/v1/commitment-check", json=_DEAL).json()["id"]
        r1 = client.post(f"/api/v1/commitment-check/{cid}/sign", json={"decision": "declined"})
        assert r1.status_code == 200 and r1.json()["signed_decision"] == "declined"
        r2 = client.post(f"/api/v1/commitment-check/{cid}/sign", json={"decision": "accepted"})
        assert r2.status_code == 409  # immutable decision
    finally:
        from app.main import app

        app.dependency_overrides.clear()


# ── error: a non-allowed role cannot run a commitment check (403) ─────────────────
def test_commitment_role_gate_403(tenant, monkeypatch):
    user_id = str(uuid.uuid4())
    asyncio.run(_seed_user(tenant, user_id))
    client = _client(tenant, user_id, "analyst", monkeypatch)  # not in required roles
    try:
        assert client.post("/api/v1/commitment-check", json=_DEAL).status_code == 403
    finally:
        from app.main import app

        app.dependency_overrides.clear()


async def _seed_multi_entity(tenant: str) -> None:
    """One vendor (CloudCo) spending across two entities → a leverage candidate; a second
    vendor in a single entity → excluded."""
    from app.core.database import session_for_tenant
    from app.models.entity import Entity
    from app.models.spend import SpendRecord
    from app.models.vendor import Vendor

    tid = uuid.UUID(tenant)
    e1, e2 = uuid.uuid4(), uuid.uuid4()
    cloud, solo = uuid.uuid4(), uuid.uuid4()
    async with await session_for_tenant(tenant) as s:
        s.add_all([
            Entity(id=e1, tenant_id=tid, name="Entity One", type="legal_entity"),
            Entity(id=e2, tenant_id=tid, name="Entity Two", type="legal_entity"),
            Vendor(id=cloud, tenant_id=tid, name="CloudCo", normalized_name="cloudco",
                   name_fingerprint="cloudco"),
            Vendor(id=solo, tenant_id=tid, name="SoloVendor", normalized_name="solovendor",
                   name_fingerprint="solovendor"),
        ])
        await s.flush()
        rows = [
            (cloud, e1, "1000000"), (cloud, e2, "1400000"),  # CloudCo across 2 entities
            (solo, e1, "500000"),  # SoloVendor only in e1
        ]
        for i, (vid, eid, amt) in enumerate(rows):
            s.add(SpendRecord(
                id=uuid.uuid4(), tenant_id=tid, vendor_id=vid, entity_id=eid,
                amount=Decimal(amt), currency="USD", spend_date=date(2026, 6, 1),
                source_system="x", source_row_hash=f"h{i}",
            ))
        await s.commit()


# ── positive: vendor leverage finds multi-entity vendor; excludes single-entity ───
def test_portfolio_vendor_leverage(tenant, monkeypatch):
    asyncio.run(_seed_user(tenant, str(uuid.uuid4())))
    asyncio.run(_seed_multi_entity(tenant))
    user_id = str(uuid.uuid4())
    client = _client(tenant, user_id, "portfolio_admin", monkeypatch)
    try:
        r = client.get("/api/v1/portfolio/vendor-leverage")
        assert r.status_code == 200
        vendors = r.json()["vendors"]
        assert len(vendors) == 1  # only CloudCo (2 entities); SoloVendor excluded
        cloud = vendors[0]
        assert cloud["vendor"] == "CloudCo"
        assert cloud["entity_count"] == 2
        assert Decimal(cloud["total_spend"]) == Decimal("2400000")  # 1.0M + 1.4M
        assert "no external pricing" in cloud["note"]  # first-party guarantee
    finally:
        from app.main import app

        app.dependency_overrides.clear()


# ── error: portfolio governance is RBAC-gated to portfolio_admin/admin (403) ──────
def test_portfolio_rbac_403(tenant, monkeypatch):
    asyncio.run(_seed_user(tenant, str(uuid.uuid4())))
    user_id = str(uuid.uuid4())
    client = _client(tenant, user_id, "analyst", monkeypatch)  # not portfolio_admin
    try:
        assert client.get("/api/v1/portfolio/vendor-leverage").status_code == 403
    finally:
        from app.main import app

        app.dependency_overrides.clear()


# ── degradation endpoint reflects marked subsystems (graceful degradation, §15.1) ─
def test_health_degradation_reports_state(tenant, monkeypatch):
    from app.core.degradation import degradation_service

    user_id = str(uuid.uuid4())
    asyncio.run(_seed_user(tenant, user_id))
    client = _client(tenant, user_id, "admin", monkeypatch)
    try:
        degradation_service.mark_degraded("model_provider", "3 consecutive timeouts")
        body = client.get("/health/degradation").json()  # health router mounts at root
        subs = [d["subsystem"] for d in body["degraded"]]
        assert "model_provider" in subs and body["healthy"] is False
    finally:
        degradation_service.mark_healthy("model_provider")
        from app.main import app

        app.dependency_overrides.clear()


def test_commitment_check_advisory_record_immutable(tenant, monkeypatch):
    """commitment_checks is no-delete — the advisory audit record cannot be erased."""
    user_id = str(uuid.uuid4())
    asyncio.run(_seed_user(tenant, user_id))
    client = _client(tenant, user_id, "cfo", monkeypatch)
    try:
        cid = client.post("/api/v1/commitment-check", json=_DEAL).json()["id"]
    finally:
        from app.main import app

        app.dependency_overrides.clear()

    admin = _admin()
    with admin.cursor() as cur:
        cur.execute("DELETE FROM commitment_checks WHERE id=%s", (cid,))
        cur.execute("SELECT count(*) FROM commitment_checks WHERE id=%s", (cid,))
        assert cur.fetchone()[0] == 1  # DELETE did INSTEAD NOTHING — still present
    admin.close()
