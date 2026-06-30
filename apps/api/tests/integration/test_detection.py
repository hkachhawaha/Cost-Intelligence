"""Phase 3 detection integration tests (live Postgres, migration 004 applied).

Seeds reconciled data, runs DetectionService.run_all_rules, and checks opportunity
creation, idempotency, confidence propagation, the lifecycle state machine, and
tenant isolation.

Run: RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_detection.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.conftest import requires_db

pytestmark = requires_db

TODAY = date(2026, 6, 30)


def _dsn() -> str:
    from app.core.config import settings

    return settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")


def _admin():
    import psycopg

    return psycopg.connect(_dsn(), autocommit=True)


async def _seed(tenant_id: str):
    from app.core.database import session_for_tenant
    from app.models.contract import Contract
    from app.models.matching import MatchResult
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
            Vendor(
                id=v, tenant_id=tid, name="Acme", normalized_name="acme", name_fingerprint="acme"
            )
        )
        await s.flush()

        c1, c2 = uuid.uuid4(), uuid.uuid4()
        # C1: auto-renewal in window + uplift creep (confidence 1.0, no match needed)
        s.add(
            Contract(
                id=c1,
                tenant_id=tid,
                vendor_id=v,
                acv=Decimal("1000000"),
                currency="USD",
                start_date=date(2025, 7, 1),
                end_date=TODAY,
                renewal_type="auto",
                renewal_notice_days=30,
                uplift_pct=Decimal("0.07"),
                status="active",
                source_system="sheets",
                source_row_hash="c1",
            )
        )
        # C2: unused commitment, confidence inherited from a 0.80 match
        s.add(
            Contract(
                id=c2,
                tenant_id=tid,
                vendor_id=v,
                acv=Decimal("100000"),
                currency="USD",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                renewal_type="none",
                yearly_commit=Decimal("100000"),
                status="active",
                source_system="sheets",
                source_row_hash="c2",
            )
        )
        await s.flush()

        spend_id = uuid.uuid4()
        s.add(
            SpendRecord(
                id=spend_id,
                tenant_id=tid,
                vendor_id=v,
                vendor_name_raw="Acme",
                amount=Decimal("80000"),
                currency="USD",
                spend_date=date(2026, 3, 1),
                source_system="sheets",
                source_row_hash="s2",
            )
        )
        await s.flush()
        s.add(
            MatchResult(
                tenant_id=tid,
                spend_id=spend_id,
                contract_id=c2,
                method="vendor_amount_date",
                scenario=1,
                confidence=Decimal("0.800"),
                status="spot_check",
            )
        )
        await s.commit()


async def _detect(tenant_id: str):
    from app.core.database import session_for_tenant
    from app.services.detection import DetectionService
    from app.services.scoring import ScoringService

    async with await session_for_tenant(tenant_id) as s:
        svc = DetectionService(s, ScoringService())
        opps = await svc.run_all_rules(tenant_id, today=TODAY)
        await s.commit()
        return opps


@pytest.fixture()
def tenant():
    tid = str(uuid.uuid4())
    yield tid
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "TRUNCATE tenants, vendors, contracts, spend_records, match_results, "
            "opportunities, recovery_items, agent_runs, audit_events CASCADE"
        )
    admin.close()


async def test_detection_creates_and_propagates_confidence(tenant):
    await _seed(tenant)
    await _detect(tenant)

    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT type, impact, confidence FROM opportunities WHERE tenant_id=%s", (tenant,)
        )
        rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        assert "auto_renewal" in rows and float(rows["auto_renewal"][0]) == 70000.0
        assert "uplift_creep" in rows
        # unused_commitment inherits the 0.80 match confidence (min-of-chain)
        assert "unused_commitment" in rows
        assert float(rows["unused_commitment"][1]) == 0.8
        assert float(rows["unused_commitment"][0]) == 20000.0
    admin.close()


async def test_detection_idempotent(tenant):
    await _seed(tenant)
    await _detect(tenant)
    await _detect(tenant)  # re-run
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM opportunities WHERE tenant_id=%s", (tenant,))
        first = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM opportunities WHERE tenant_id=%s AND type='auto_renewal'",
            (tenant,),
        )
        assert cur.fetchone()[0] == 1  # no duplicate per (type, contract)
        assert first >= 3
    admin.close()


async def test_status_machine_enforces_transitions(tenant):
    from sqlalchemy import select

    from app.core.database import session_for_tenant
    from app.models.opportunity import Opportunity
    from app.services.opportunity_status import IllegalTransition, OpportunityStatusService

    await _seed(tenant)
    await _detect(tenant)
    principal = SimpleNamespace(user_id=str(uuid.uuid4()))
    async with await session_for_tenant(tenant) as s:
        opp = (
            await s.execute(select(Opportunity).where(Opportunity.type == "auto_renewal"))
        ).scalar_one()
        svc = OpportunityStatusService(s)
        # legal: detected → triaged
        await svc.transition(opp, "triaged", principal)
        assert opp.status == "triaged"
        # illegal: triaged → realized (must go through in_progress)
        with pytest.raises(IllegalTransition):
            await svc.transition(opp, "realized", principal)
        await s.rollback()


def test_detection_rls_isolation(tenant):
    import asyncio

    import psycopg

    asyncio.run(_seed(tenant))
    asyncio.run(_detect(tenant))

    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rls_app_user') "
            "THEN CREATE ROLE rls_app_user LOGIN PASSWORD 'rls_test' NOSUPERUSER; END IF; END $$;"
        )
        cur.execute("GRANT USAGE ON SCHEMA public TO rls_app_user")
        cur.execute("GRANT SELECT ON opportunities TO rls_app_user")
    admin.close()

    host = _dsn().split("://", 1)[1].split("@", 1)[1]
    conn = psycopg.connect(f"postgresql://rls_app_user:rls_test@{host}", autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (tenant,))
            cur.execute("SELECT count(*) FROM opportunities")
            assert cur.fetchone()[0] >= 3
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (str(uuid.uuid4()),))
            cur.execute("SELECT count(*) FROM opportunities")
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()
