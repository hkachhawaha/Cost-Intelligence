"""Phase 5 read-model API tests (§14.3) — live Postgres + Redis, migration 005.

Exercises the UI read endpoints end-to-end through the real FastAPI app (RBAC +
response schemas + read-model query services), proving every module reads from the
Phase-4 memory layer / canonical store and the opportunity workflow enforces §8.3.

Auth + tenant binding are injected via dependency overrides: `get_current_principal`
returns a wildcard principal and `get_session` yields a tenant-bound (RLS) session,
so requests behave exactly as an authenticated, tenant-scoped call would.

Run: RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_read_models.py -v
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


def _dsn() -> str:
    from app.core.config import settings

    return settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")


def _admin():
    import psycopg

    return psycopg.connect(_dsn(), autocommit=True)


def _clear_redis(tenant_id: str) -> None:
    import redis as redis_sync

    from app.core.config import settings

    r = redis_sync.from_url(str(settings.redis_url))
    keys = [
        f"kpis:{tenant_id}",
        f"memver:{tenant_id}",
        *r.scan_iter(match=f"section:{tenant_id}:*"),
    ]
    if keys:
        r.delete(*keys)
    r.close()


async def _seed(tenant_id: str) -> None:
    """Tenant with 2 contracts (1 active in-range, 1 expired), 2 matched spend rows,
    2 opportunities (savings + recovery) and a recovery item."""
    from app.core.database import session_for_tenant
    from app.models.contract import Contract
    from app.models.matching import MatchResult
    from app.models.opportunity import Opportunity, RecoveryItem
    from app.models.spend import SpendRecord
    from app.models.tenant import Tenant
    from app.models.vendor import Vendor

    async with await session_for_tenant(tenant_id) as s:
        tid = uuid.UUID(tenant_id)
        s.add(
            Tenant(id=tid, name="Acme", slug=f"acme{tenant_id[:8]}", encryption_key_ref="kms://t")
        )
        await s.flush()
        v = uuid.uuid4()
        s.add(
            Vendor(id=v, tenant_id=tid, name="Acme", normalized_name="acme", name_fingerprint="a")
        )
        await s.flush()

        c1, c2 = uuid.uuid4(), uuid.uuid4()
        s.add(
            Contract(
                id=c1,
                tenant_id=tid,
                vendor_id=v,
                acv=Decimal("1000000"),
                tcv=Decimal("3000000"),
                currency="USD",
                start_date=date(2025, 7, 1),
                end_date=date(2026, 12, 31),
                renewal_type="auto",
                renewal_notice_days=30,
                status="active",
                source_system="sheets",
                source_row_hash="c1",
            )
        )
        s.add(
            Contract(
                id=c2,
                tenant_id=tid,
                vendor_id=v,
                acv=Decimal("100000"),
                tcv=Decimal("100000"),
                currency="USD",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
                renewal_type="none",
                status="expired",
                source_system="sheets",
                source_row_hash="c2",
            )
        )
        await s.flush()

        s1_id, s2_id = uuid.uuid4(), uuid.uuid4()
        s.add(
            SpendRecord(
                id=s1_id,
                tenant_id=tid,
                vendor_id=v,
                vendor_name_raw="Acme",
                amount=Decimal("60000"),
                currency="USD",
                spend_date=date(2026, 3, 1),
                po_number="PO-1",
                gl_code="6000-SaaS",
                cost_center="CC-1",
                source_system="sheets",
                source_row_hash="s1",
            )
        )
        s.add(
            SpendRecord(
                id=s2_id,
                tenant_id=tid,
                vendor_id=v,
                vendor_name_raw="Acme",
                amount=Decimal("40000"),
                currency="USD",
                spend_date=date(2026, 3, 1),
                gl_code="6200-Cloud",
                cost_center="CC-2",
                source_system="sheets",
                source_row_hash="s2",
            )
        )
        await s.flush()

        s.add(
            MatchResult(
                tenant_id=tid,
                spend_id=s1_id,
                contract_id=c1,
                method="po_exact",
                scenario=1,
                confidence=Decimal("0.990"),
                status="accepted",
            )
        )
        s.add(
            MatchResult(
                tenant_id=tid,
                spend_id=s2_id,
                contract_id=c2,
                method="vendor_amount_date",
                scenario=1,
                confidence=Decimal("0.850"),
                status="accepted",
            )
        )
        rec_opp = uuid.uuid4()
        s.add(
            Opportunity(
                tenant_id=tid,
                contract_id=c1,
                vendor_id=v,
                type="uplift_creep",
                bucket="savings",
                impact=Decimal("30000"),
                confidence=Decimal("0.900"),
                status="detected",
            )
        )
        s.add(
            Opportunity(
                id=rec_opp,
                tenant_id=tid,
                contract_id=c2,
                vendor_id=v,
                type="duplicate_invoice",
                bucket="recovery",
                impact=Decimal("20000"),
                confidence=Decimal("0.800"),
                status="detected",
            )
        )
        await s.flush()
        s.add(
            RecoveryItem(
                tenant_id=tid,
                opp_id=rec_opp,
                vendor_id=v,
                amount=Decimal("20000"),
                status="detected",
                evidence={"formula": "invoice_amount × (occurrences − 1)", "occurrences": 2},
            )
        )
        await s.commit()


async def _build(tenant_id: str) -> None:
    from app.core.agent_run import agent_run
    from app.core.database import session_for_tenant
    from app.core.kpi_cache import RedisKpiCache
    from app.core.redis import get_redis
    from app.services.memory import MemoryService
    from app.services.memory_kpis import KpiComputer

    redis = get_redis()
    async with agent_run(tenant_id=tenant_id, agent="memory_build", trigger="manual") as run:
        async with await session_for_tenant(tenant_id) as s:
            svc = MemoryService(s, RedisKpiCache(redis), KpiComputer(s))
            await svc.build(tenant_id, build_run_id=str(run.run_id))
    await redis.aclose()


@pytest.fixture()
def tenant():
    tid = str(uuid.uuid4())
    yield tid
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "TRUNCATE tenants, vendors, contracts, spend_records, match_results, "
            "opportunities, recovery_items, tenant_memory, memory_embeddings, sync_runs, "
            "agent_runs, audit_events CASCADE"
        )
    admin.close()
    _clear_redis(tid)


@pytest.fixture()
def client(tenant, monkeypatch):
    from app.core import auth as auth_mod
    from app.core.auth import Principal, get_current_principal
    from app.core.database import get_session, session_for_tenant

    async def _noop():
        return None

    monkeypatch.setattr(auth_mod.jwks_cache, "_refresh", _noop)

    async def _principal() -> Principal:
        return Principal(
            user_id=str(uuid.uuid4()),
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

    from app.main import app

    app.dependency_overrides[get_current_principal] = _principal
    app.dependency_overrides[get_session] = _session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_dashboard_kpis_from_memory(client, tenant):
    asyncio.run(_seed(tenant))
    asyncio.run(_build(tenant))
    r = client.get("/api/v1/dashboard/kpis")
    assert r.status_code == 200
    body = r.json()
    assert body["initialized"] is True
    assert Decimal(body["total_identified"]) == Decimal("50000.00")
    assert Decimal(body["total_spend"]) == Decimal("100000.00")
    assert Decimal(body["spend_under_management_pct"]) == Decimal("60.00")


def test_dashboard_reads_memory_not_source(client, tenant):
    # Flush the Redis cache → the endpoint must still serve from Postgres memory
    # (never re-query a source system). Proves the §5.8 memory-layer source.
    asyncio.run(_seed(tenant))
    asyncio.run(_build(tenant))
    _clear_redis(tenant)
    r = client.get("/api/v1/dashboard/kpis")
    assert r.status_code == 200
    assert r.json()["initialized"] is True
    assert Decimal(r.json()["total_identified"]) == Decimal("50000.00")


def test_spend_by_category_shape(client, tenant):
    asyncio.run(_seed(tenant))
    asyncio.run(_build(tenant))
    r = client.get("/api/v1/spend/by-category")
    assert r.status_code == 200
    body = r.json()
    assert body["dimension"] == "category"
    amounts = [Decimal(i["amount"]) for i in body["items"]]
    assert amounts == sorted(amounts, reverse=True)  # sorted desc by amount
    assert {i["label"] for i in body["items"]} == {"6000-SaaS", "6200-Cloud"}


def test_contract_spend_utilization(client, tenant):
    asyncio.run(_seed(tenant))
    asyncio.run(_build(tenant))
    contracts = client.get("/api/v1/contracts").json()["items"]
    c1 = next(c for c in contracts if c["acv"] == "1000000.00")
    r = client.get(f"/api/v1/contracts/{c1['id']}/spend")
    assert r.status_code == 200
    body = r.json()
    # $60k matched against $1M ACV → 6.00% utilization.
    assert Decimal(body["total_matched_spend"]) == Decimal("60000.00")
    assert Decimal(body["utilization_pct"]) == Decimal("6.00")
    assert len(body["lines"]) == 1


def test_renewals_window_filter(client, tenant):
    asyncio.run(_seed(tenant))
    asyncio.run(_build(tenant))
    # window=90 returns only within_90; window=365 returns all three buckets.
    r90 = client.get("/api/v1/renewals?window=90")
    assert r90.status_code == 200
    assert set(r90.json().keys()) == {"within_90", "within_180", "within_365"}
    r365 = client.get("/api/v1/renewals?window=365")
    assert r365.status_code == 200
    # c1 ends 2026-12-31 → lands in one of the buckets; total entries == 1 across all.
    total = sum(len(r365.json()[k]) for k in ("within_90", "within_180", "within_365"))
    assert total == 1
    # bad window → 422
    assert client.get("/api/v1/renewals?window=45").status_code == 422


def test_recovery_packs_grouping(client, tenant):
    asyncio.run(_seed(tenant))
    asyncio.run(_build(tenant))
    r = client.get("/api/v1/recovery/packs")
    assert r.status_code == 200
    packs = r.json()["packs"]
    assert len(packs) == 1
    pack = packs[0]
    # total == Σ item.amount
    assert Decimal(pack["total"]) == sum(Decimal(i["amount"]) for i in pack["items"])
    assert Decimal(pack["total"]) == Decimal("20000.00")


def test_status_illegal_transition_409(client, tenant):
    asyncio.run(_seed(tenant))
    asyncio.run(_build(tenant))
    opp = client.get("/api/v1/opportunities?sort=ranked").json()["items"][0]
    assert opp["status"] == "detected"
    # detected → realized is illegal (must pass through triaged/in_progress).
    r = client.patch(f"/api/v1/opportunities/{opp['id']}/status", json={"status": "realized"})
    assert r.status_code == 409


def test_status_transition_audited(client, tenant):
    asyncio.run(_seed(tenant))
    asyncio.run(_build(tenant))
    opp = client.get("/api/v1/opportunities?sort=ranked").json()["items"][0]
    r = client.patch(f"/api/v1/opportunities/{opp['id']}/status", json={"status": "triaged"})
    assert r.status_code == 200
    assert r.json()["status"] == "triaged"
    # A legal transition writes an audit_event with actor='human'.
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT actor, payload->>'to' FROM audit_events "
            "WHERE event_type='opportunity.status_changed' AND tenant_id=%s",
            (tenant,),
        )
        rows = cur.fetchall()
    admin.close()
    assert any(actor == "human" and to == "triaged" for actor, to in rows)
