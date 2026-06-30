"""Phase 7 integration tests (§14.2) — live Postgres, migration 007.

Deterministic, no LLM key needed: consolidation fragmentation scoring, the first-party
exposure formula, portfolio RBAC, and the human-gated extraction verification (promotion
writes the verified fields to canonical + an AuditEvent).

Run: RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_advanced.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

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
            "opportunities, index_register, extraction_queue, anomaly_flags, "
            "steward_proposals, agent_runs, audit_events CASCADE"
        )
    admin.close()


async def _seed_tenant(tid: str):
    from app.core.database import session_for_tenant
    from app.models.tenant import Tenant

    async with await session_for_tenant(tid) as s:
        s.add(
            Tenant(
                id=uuid.UUID(tid), name="Acme", slug=f"acme{tid[:8]}", encryption_key_ref="kms://t"
            )
        )
        await s.commit()


async def test_consolidation_fragmentation_score(tenant):
    """A category split across many vendors scores high; a 2-vendor category is excluded
    by the MIN_VENDORS threshold."""
    from app.core.database import session_for_tenant
    from app.models.spend import SpendRecord
    from app.models.vendor import Vendor
    from app.services.vendors import vendor_service

    await _seed_tenant(tenant)
    tid = uuid.UUID(tenant)
    async with await session_for_tenant(tenant) as s:
        # "IT & Software": 4 vendors × $20k each ($80k total, evenly split → frag ~0.75).
        for i in range(4):
            vid = uuid.uuid4()
            s.add(
                Vendor(
                    id=vid,
                    tenant_id=tid,
                    name=f"IT Vendor {i}",
                    normalized_name=f"it{i}",
                    name_fingerprint=f"it{i}",
                )
            )
            await s.flush()  # vendor must exist before the spend_records FK
            s.add(
                SpendRecord(
                    id=uuid.uuid4(),
                    tenant_id=tid,
                    vendor_id=vid,
                    vendor_name_raw=f"IT {i}",
                    amount=Decimal("20000"),
                    base_amount=Decimal("20000"),
                    taxonomy_l1="IT & Software",
                    currency="USD",
                    spend_date=date(2026, 3, 1),
                    source_system="x",
                    source_row_hash=f"it{i}",
                )
            )
        # "Facilities": only 2 vendors → below MIN_VENDORS (3) → excluded.
        for i in range(2):
            vid = uuid.uuid4()
            s.add(
                Vendor(
                    id=vid,
                    tenant_id=tid,
                    name=f"Fac {i}",
                    normalized_name=f"fac{i}",
                    name_fingerprint=f"fac{i}",
                )
            )
            await s.flush()  # vendor must exist before the spend_records FK
            s.add(
                SpendRecord(
                    id=uuid.uuid4(),
                    tenant_id=tid,
                    vendor_id=vid,
                    vendor_name_raw=f"Fac {i}",
                    amount=Decimal("40000"),
                    base_amount=Decimal("40000"),
                    taxonomy_l1="Facilities",
                    currency="USD",
                    spend_date=date(2026, 3, 1),
                    source_system="x",
                    source_row_hash=f"fac{i}",
                )
            )
        await s.commit()

        principal = SimpleNamespace(tenant_id=tenant, entity_id=None, role="cfo")
        candidates = await vendor_service.consolidation_candidates(s, principal)

    keys = {c.key for c in candidates}
    assert "IT & Software" in keys  # 4 vendors, $80k → candidate
    assert "Facilities" not in keys  # 2 vendors → below threshold
    it = next(c for c in candidates if c.key == "IT & Software")
    assert it.vendor_count == 4
    # 4 even vendors → largest share 0.25 → fragmentation 0.75.
    assert abs(it.fragmentation_score - Decimal("0.75")) < Decimal("0.01")


async def test_exposure_first_party_formula(tenant):
    """indexed_exposure == ACV × indexed_share × (move_pct/100), exactly — no external feed."""
    from app.core.database import session_for_tenant
    from app.models.advanced import IndexRegisterEntry
    from app.models.contract import Contract
    from app.models.vendor import Vendor
    from app.services.indexation import indexation_service

    await _seed_tenant(tenant)
    tid = uuid.UUID(tenant)
    cid, vid = uuid.uuid4(), uuid.uuid4()
    async with await session_for_tenant(tenant) as s:
        s.add(
            Vendor(
                id=vid,
                tenant_id=tid,
                name="Acme Cloud",
                normalized_name="acme",
                name_fingerprint="acme",
            )
        )
        await s.flush()  # vendor must exist before the contract FK
        s.add(
            Contract(
                id=cid,
                tenant_id=tid,
                vendor_id=vid,
                acv=Decimal("240000"),
                currency="USD",
                start_date=date(2025, 1, 1),
                end_date=date(2026, 12, 31),
                status="active",
                source_system="x",
                source_row_hash="c1",
            )
        )
        await s.flush()  # contract must exist before the index_register FK
        s.add(
            IndexRegisterEntry(
                id=uuid.uuid4(),
                tenant_id=tid,
                contract_id=cid,
                index_type="CPI",
                indexed_share=0.36,
            )
        )
        await s.commit()

        principal = SimpleNamespace(tenant_id=tenant, entity_id=None, role="cfo")
        result = await indexation_service.exposure(s, principal, move_pct=Decimal("10"))

    # 240000 × 0.36 × 0.10 = 8640.00 exactly.
    assert result.total_indexed_exposure == Decimal("8640.00")
    assert result.lines[0].indexed_exposure == Decimal("8640.00")
    assert result.lines[0].formula == "ACV × indexed_share × assumed_move"


async def test_portfolio_rbac(tenant):
    from app.core.database import session_for_tenant
    from app.services.portfolio import NotAuthorized, portfolio_service

    await _seed_tenant(tenant)
    async with await session_for_tenant(tenant) as s:
        with pytest.raises(NotAuthorized):
            await portfolio_service.by_entity(
                s, SimpleNamespace(tenant_id=tenant, entity_id=None, role="analyst")
            )
        # portfolio_admin is allowed (no rows seeded → empty list, but no raise).
        rows = await portfolio_service.by_entity(
            s, SimpleNamespace(tenant_id=tenant, entity_id=None, role="portfolio_admin")
        )
        assert rows == []


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
            user_id=user_id,
            tenant_id=tenant,
            role=role,
            entity_id=None,
            email="u@acme.com",
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


def test_extraction_human_verification(tenant, monkeypatch):
    """Extracted terms never reach canonical until a human (legal/admin) promotes them;
    promotion applies edited fields + writes AuditEvent(extraction.promoted, actor=human).
    A non-legal role is refused (403)."""
    import asyncio

    from app.core.database import session_for_tenant
    from app.models.advanced import ExtractionQueueItem
    from app.models.contract import Contract
    from app.models.user import User
    from app.models.vendor import Vendor

    user_id = str(uuid.uuid4())
    cid, qid = uuid.uuid4(), uuid.uuid4()

    async def _seed():
        await _seed_tenant(tenant)
        tid = uuid.UUID(tenant)
        vid = uuid.uuid4()
        async with await session_for_tenant(tenant) as s:
            s.add(
                User(
                    id=uuid.UUID(user_id),
                    tenant_id=tid,
                    auth0_id=f"auth0|{user_id[:8]}",
                    email="legal@acme.com",
                )
            )
            s.add(
                Vendor(
                    id=vid,
                    tenant_id=tid,
                    name="Acme",
                    normalized_name="acme",
                    name_fingerprint="acme",
                )
            )
            await s.flush()
            s.add(
                Contract(
                    id=cid,
                    tenant_id=tid,
                    vendor_id=vid,
                    acv=Decimal("240000"),
                    uplift_pct=Decimal("0.10"),
                    currency="USD",
                    start_date=date(2025, 1, 1),
                    end_date=date(2026, 12, 31),
                    status="active",
                    source_system="x",
                    source_row_hash="c1",
                )
            )
            await s.flush()  # ensure the contract exists before the FK from the queue item
            s.add(
                ExtractionQueueItem(
                    id=qid,
                    tenant_id=tid,
                    contract_id=cid,
                    source_document="s3://doc.pdf",
                    extracted_fields={"uplift_pct": "0.10", "renewal_type": "auto"},
                    status="needs_verification",
                )
            )
            await s.commit()

    asyncio.run(_seed())

    # A non-legal role cannot verify.
    denied = _client(tenant, user_id, "analyst", monkeypatch)
    try:
        r = denied.post(
            f"/api/v1/extraction/verification-queue/{qid}/verify", json={"action": "promote"}
        )
        assert r.status_code == 403
    finally:
        from app.main import app

        app.dependency_overrides.clear()

    # Legal promotes with an edit (uplift 0.10 → 0.08).
    client = _client(tenant, user_id, "legal", monkeypatch)
    try:
        r = client.post(
            f"/api/v1/extraction/verification-queue/{qid}/verify",
            json={"action": "promote", "edited_fields": {"uplift_pct": "0.08"}},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "promoted"

        admin = _admin()
        with admin.cursor() as cur:
            cur.execute("SELECT uplift_pct FROM contracts WHERE id=%s", (str(cid),))
            assert float(cur.fetchone()[0]) == 0.08  # edited value won, written to canonical
            cur.execute("SELECT status FROM extraction_queue WHERE id=%s", (str(qid),))
            assert cur.fetchone()[0] == "promoted"
            cur.execute(
                "SELECT actor FROM audit_events WHERE event_type='extraction.promoted' "
                "AND tenant_id=%s",
                (tenant,),
            )
            assert any(a == "human" for (a,) in cur.fetchall())
        admin.close()
    finally:
        from app.main import app

        app.dependency_overrides.clear()
