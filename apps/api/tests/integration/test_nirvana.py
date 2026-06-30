"""Phase 6 NirvanaI integration tests (§14.2) — live Postgres + Redis, migration 006.

Covers the security-critical, deterministic paths (no LLM key needed): RAG RBAC/entity
scoping enforced BEFORE retrieval, the human-gated draft-send audit trail, and the
ModelGateway per-tenant rate-limit circuit breaker.

Run: RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_nirvana.py -v
"""

from __future__ import annotations

import time
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requires_db

pytestmark = requires_db


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
        cur.execute(
            "TRUNCATE tenants, entities, users, vendors, contracts, spend_records, "
            "opportunities, recovery_items, document_drafts, nirvana_conversations, "
            "nirvana_messages, model_usage_events, agent_runs, audit_events CASCADE"
        )
    admin.close()


async def _seed_two_entities(tenant_id: str):
    """One vendor, two entities, a contract each. Returns (entity_a, contract_a, contract_b)."""
    from app.core.database import session_for_tenant
    from app.models.contract import Contract
    from app.models.entity import Entity
    from app.models.tenant import Tenant
    from app.models.vendor import Vendor

    tid = uuid.UUID(tenant_id)
    ent_a, ent_b = uuid.uuid4(), uuid.uuid4()
    c_a, c_b = uuid.uuid4(), uuid.uuid4()
    v = uuid.uuid4()
    async with await session_for_tenant(tenant_id) as s:
        s.add(
            Tenant(id=tid, name="Acme", slug=f"acme{tenant_id[:8]}", encryption_key_ref="kms://t")
        )
        await s.flush()
        s.add(Entity(id=ent_a, tenant_id=tid, name="Div A", type="business_unit"))
        s.add(Entity(id=ent_b, tenant_id=tid, name="Div B", type="business_unit"))
        s.add(
            Vendor(id=v, tenant_id=tid, name="Acme", normalized_name="acme", name_fingerprint="a")
        )
        await s.flush()
        for cid, ent in ((c_a, ent_a), (c_b, ent_b)):
            s.add(
                Contract(
                    id=cid,
                    tenant_id=tid,
                    vendor_id=v,
                    entity_id=ent,
                    acv=Decimal("100000"),
                    currency="USD",
                    start_date=date(2025, 1, 1),
                    end_date=date(2026, 12, 31),
                    status="active",
                    source_system="sheets",
                    source_row_hash=str(cid),
                )
            )
        await s.commit()
    return str(ent_a), str(c_a), str(c_b)


async def test_rag_rbac_scope(tenant):
    """A scoped (entity A) user's authorized set excludes entity B's contract; a
    portfolio role sees both. Access control is resolved BEFORE the vector search."""
    from types import SimpleNamespace

    from app.core.database import session_for_tenant
    from app.services.rag import rag_service

    ent_a, c_a, c_b = await _seed_two_entities(tenant)
    async with await session_for_tenant(tenant) as s:
        scoped = SimpleNamespace(tenant_id=tenant, entity_id=ent_a, role="analyst")
        ids = await rag_service._authorized_contract_ids(s, scoped)
        assert c_a in ids and c_b not in ids  # entity A only

        cfo = SimpleNamespace(tenant_id=tenant, entity_id=None, role="cfo")
        ids_all = await rag_service._authorized_contract_ids(s, cfo)
        assert c_a in ids_all and c_b in ids_all  # portfolio role sees all


async def test_gateway_rate_limit_trips(tenant):
    """Over-budget tenant trips the per-minute circuit breaker (RateLimitExceeded)."""
    from app.core.config import settings
    from app.core.model_gateway import RateLimitExceeded, model_gateway
    from app.core.redis import get_redis

    window_key = f"mg:budget:{tenant}:{int(time.time() // 60)}"
    redis = get_redis()
    await redis.set(window_key, settings.model_tokens_per_minute_per_tenant + 1, ex=120)
    await redis.aclose()
    with pytest.raises(RateLimitExceeded):
        await model_gateway._enforce_budget(tenant)


def _client(tenant: str, user_id: str, monkeypatch) -> TestClient:
    from app.core import auth as auth_mod
    from app.core.auth import Principal, get_current_principal
    from app.core.database import get_session, session_for_tenant
    from app.main import app

    async def _noop():
        return None

    monkeypatch.setattr(auth_mod.jwks_cache, "_refresh", _noop)

    async def _principal() -> Principal:
        return Principal(
            user_id=user_id,
            tenant_id=tenant,
            role="cfo",
            entity_id=None,
            email="cfo@acme.com",
            permissions=("*",),
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


def test_draft_send_is_human_gated_and_audited(tenant, monkeypatch):
    """A draft is created status='draft' with no sender; only a human PATCH status='sent'
    sets sent_by/sent_at and writes AuditEvent(document.sent, actor=human); sent is immutable."""
    import asyncio
    import uuid as _uuid

    from app.core.database import session_for_tenant
    from app.models.nirvana import DocumentDraft
    from app.models.tenant import Tenant
    from app.models.user import User

    user_id = str(_uuid.uuid4())
    draft_id = _uuid.uuid4()

    async def _seed():
        tid = _uuid.UUID(tenant)
        async with await session_for_tenant(tenant) as s:
            s.add(
                Tenant(id=tid, name="Acme", slug=f"acme{tenant[:8]}", encryption_key_ref="kms://t")
            )
            await s.flush()
            s.add(
                User(
                    id=_uuid.UUID(user_id),
                    tenant_id=tid,
                    auth0_id=f"auth0|{user_id[:8]}",
                    email="cfo@acme.com",
                )
            )
            await s.flush()
            s.add(
                DocumentDraft(
                    id=draft_id,
                    tenant_id=tid,
                    user_id=_uuid.UUID(user_id),
                    template="renegotiation",
                    context_ref={"type": "opportunity", "id": "x"},
                    title="Renegotiation Request — Acme",
                    body_markdown="Dear Acme…",
                    citations=[],
                    status="draft",
                )
            )
            await s.commit()

    asyncio.run(_seed())

    client = _client(tenant, user_id, monkeypatch)
    try:
        # Draft starts un-sent.
        admin = _admin()
        with admin.cursor() as cur:
            cur.execute("SELECT status, sent_by FROM document_drafts WHERE id=%s", (str(draft_id),))
            status_, sent_by = cur.fetchone()
            assert status_ == "draft" and sent_by is None

        # Human marks it sent.
        r = client.patch(f"/api/v1/nirvana/drafts/{draft_id}", json={"status": "sent"})
        assert r.status_code == 200
        assert r.json()["status"] == "sent"

        with admin.cursor() as cur:
            cur.execute("SELECT sent_by FROM document_drafts WHERE id=%s", (str(draft_id),))
            assert cur.fetchone()[0] is not None  # sent_by recorded
            cur.execute(
                "SELECT actor FROM audit_events WHERE event_type='document.sent' AND tenant_id=%s",
                (tenant,),
            )
            assert any(actor == "human" for (actor,) in cur.fetchall())
        admin.close()

        # Sent drafts are immutable.
        r2 = client.patch(f"/api/v1/nirvana/drafts/{draft_id}", json={"body_markdown": "edit"})
        assert r2.status_code == 409
    finally:
        from app.main import app

        app.dependency_overrides.clear()
