"""Phase 4 memory-layer integration tests (live Postgres + Redis, migration 005).

Covers the §5.8 "ingest-once, operate-from-memory" contract:
  - MemoryService.build computes every KPI deterministically into tenant_memory
  - get_kpis is Redis-first and degrades to Postgres when the cache is cold
  - mark_stale raises the UI banner WITHOUT discarding intelligence
  - the AgentRun lifecycle wrapper transitions running → completed | failed
  - SyncService enforces one running sync per tenant
  - tenant_memory is RLS-isolated (verified via a non-superuser role)

Run: RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_memory.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.conftest import requires_db

pytestmark = requires_db

S1 = Decimal("60000")  # spend matched to an ACTIVE, in-range contract
S2 = Decimal("40000")  # spend matched to an EXPIRED, out-of-range contract


def _dsn() -> str:
    from app.core.config import settings

    return settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")


def _admin():
    import psycopg

    return psycopg.connect(_dsn(), autocommit=True)


async def _seed_tenant(tenant_id: str) -> None:
    """Minimal tenant row — satisfies the tenant_id FK on audit/sync tables."""
    from app.core.database import session_for_tenant
    from app.models.tenant import Tenant

    async with await session_for_tenant(tenant_id) as s:
        tid = uuid.UUID(tenant_id)
        s.add(
            Tenant(id=tid, name="Acme", slug=f"acme{tenant_id[:8]}", encryption_key_ref="kms://t")
        )
        await s.commit()


async def _seed(tenant_id: str) -> None:
    from app.core.database import session_for_tenant
    from app.models.contract import Contract
    from app.models.matching import MatchResult
    from app.models.opportunity import Opportunity
    from app.models.spend import SpendRecord
    from app.models.vendor import Vendor

    await _seed_tenant(tenant_id)
    async with await session_for_tenant(tenant_id) as s:
        tid = uuid.UUID(tenant_id)
        v = uuid.uuid4()
        s.add(
            Vendor(
                id=v, tenant_id=tid, name="Acme", normalized_name="acme", name_fingerprint="acme"
            )
        )
        await s.flush()

        c1, c2 = uuid.uuid4(), uuid.uuid4()
        s.add(
            Contract(
                id=c1,
                tenant_id=tid,
                vendor_id=v,
                acv=Decimal("1000000"),
                currency="USD",
                start_date=date(2025, 7, 1),
                end_date=date(2026, 12, 31),
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
                currency="USD",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
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
                amount=S1,
                currency="USD",
                spend_date=date(2026, 3, 1),
                po_number="PO-1",
                gl_code="6000",
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
                amount=S2,
                currency="USD",
                spend_date=date(2026, 3, 1),
                gl_code="6000",
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
                method="vendor_amount_date",
                scenario=1,
                confidence=Decimal("0.950"),
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
        await s.commit()


async def _build(tenant_id: str):
    """Mirror the production pipeline: build memory inside a memory_build agent_run
    so build_run_id references a real agent_runs row (FK)."""
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
            snapshot = await svc.build(tenant_id, build_run_id=str(run.run_id))
    await redis.aclose()
    return snapshot


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


async def test_memory_build_computes_kpis(tenant):
    await _seed(tenant)
    snap = await _build(tenant)

    # Headline figures — all computed in Python Decimal, never an LLM (§5.6).
    assert snap.total_spend == Decimal("100000.00")
    assert snap.spend_record_count == 2
    assert snap.contract_count == 2
    assert snap.vendor_count == 1
    assert snap.opportunity_count == 2
    # Both spend rows matched to a contract → 100% coverage.
    assert snap.match_coverage_pct == Decimal("100.00")
    # Only S1 ($60k) maps to an ACTIVE contract → 60% under management.
    assert snap.spend_under_management_pct == Decimal("60.00")
    # S1 is inside c1's term; S2's date is outside c2's term → 60% compliant.
    assert snap.contract_compliance_pct == Decimal("60.00")
    assert snap.total_savings == Decimal("30000.00")
    assert snap.total_recovery == Decimal("20000.00")
    assert snap.total_identified == Decimal("50000.00")
    assert snap.memory_version == 1
    # Rebuild bumps the version (idempotent figures, monotonic version).
    snap2 = await _build(tenant)
    assert snap2.memory_version == 2
    assert snap2.total_identified == Decimal("50000.00")


async def test_get_kpis_redis_then_postgres_fallback(tenant):
    from app.core.database import session_for_tenant
    from app.core.kpi_cache import RedisKpiCache
    from app.core.redis import get_redis
    from app.services.memory import MemoryService
    from app.services.memory_kpis import KpiComputer

    await _seed(tenant)
    await _build(tenant)

    redis = get_redis()
    async with await session_for_tenant(tenant) as s:
        svc = MemoryService(s, RedisKpiCache(redis), KpiComputer(s))

        # 1. Redis hot path.
        hot = await svc.get_kpis(tenant)
        assert hot["initialized"] is True
        assert Decimal(hot["total_identified"]) == Decimal("50000.00")

        # 2. Cold cache → Postgres fallback still returns the same intelligence.
        _clear_redis(tenant)
        cold = await svc.get_kpis(tenant)
        assert cold["initialized"] is True
        assert Decimal(cold["total_identified"]) == Decimal("50000.00")
    await redis.aclose()


async def test_mark_stale_keeps_intelligence(tenant):
    from app.core.database import session_for_tenant
    from app.core.kpi_cache import RedisKpiCache
    from app.core.redis import get_redis
    from app.services.memory import MemoryService
    from app.services.memory_kpis import KpiComputer

    await _seed(tenant)
    await _build(tenant)

    redis = get_redis()
    async with await session_for_tenant(tenant) as s:
        svc = MemoryService(s, RedisKpiCache(redis), KpiComputer(s))
        await svc.mark_stale(tenant)
        kpis = await svc.get_kpis(tenant)
        # Banner is raised, but the figures survive (no re-ingestion required).
        assert kpis["stale"] is True
        assert Decimal(kpis["total_identified"]) == Decimal("50000.00")
    await redis.aclose()

    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT stale, total_identified FROM tenant_memory WHERE tenant_id=%s", (tenant,)
        )
        stale, identified = cur.fetchone()
        assert stale is True
        assert float(identified) == 50000.0
    admin.close()


async def test_agent_run_lifecycle(tenant):
    from app.core.agent_run import agent_run

    await _seed_tenant(tenant)  # agent_runs.tenant_id → tenants.id

    # Happy path: running → completed, confidence + outputs recorded.
    async with agent_run(tenant_id=tenant, agent="memory_build", trigger="manual") as run:
        run.set_confidence(0.77)
        run.set_outputs({"ok": True})
    ok_id = str(run.run_id)

    # Failure path: running → failed, error captured, exception re-raised.
    with pytest.raises(ValueError):
        async with agent_run(tenant_id=tenant, agent="boom", trigger="manual") as run:
            raise ValueError("kaboom")
    fail_id = str(run.run_id)

    admin = _admin()
    with admin.cursor() as cur:
        cur.execute("SELECT status, confidence FROM agent_runs WHERE run_id=%s", (ok_id,))
        status, confidence = cur.fetchone()
        assert status == "completed"
        assert float(confidence) == 0.77
        cur.execute("SELECT status, error_message FROM agent_runs WHERE run_id=%s", (fail_id,))
        status, err = cur.fetchone()
        assert status == "failed"
        assert "kaboom" in err
    admin.close()


async def test_sync_single_running_guard(tenant):
    from app.core.database import session_for_tenant
    from app.models.memory import SyncRun
    from app.services.sync import SyncAlreadyRunningError, SyncService

    await _seed_tenant(tenant)  # sync_runs.tenant_id → tenants.id
    async with await session_for_tenant(tenant) as s:
        s.add(
            SyncRun(
                tenant_id=uuid.UUID(tenant),
                source_id=uuid.uuid4(),
                kind="initial",
                status="running",
            )
        )
        await s.commit()
        # A second start is rejected before anything is enqueued (§5.8 one-sync rule).
        with pytest.raises(SyncAlreadyRunningError):
            await SyncService(s).start(tenant, str(uuid.uuid4()), kind="refresh")


def test_memory_rls_isolation(tenant):
    import asyncio

    import psycopg

    asyncio.run(_seed(tenant))
    asyncio.run(_build(tenant))

    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rls_app_user') "
            "THEN CREATE ROLE rls_app_user LOGIN PASSWORD 'rls_test' NOSUPERUSER; END IF; END $$;"
        )
        cur.execute("GRANT USAGE ON SCHEMA public TO rls_app_user")
        cur.execute("GRANT SELECT ON tenant_memory TO rls_app_user")
    admin.close()

    host = _dsn().split("://", 1)[1].split("@", 1)[1]
    conn = psycopg.connect(f"postgresql://rls_app_user:rls_test@{host}", autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (tenant,))
            cur.execute("SELECT count(*) FROM tenant_memory")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (str(uuid.uuid4()),))
            cur.execute("SELECT count(*) FROM tenant_memory")
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()
