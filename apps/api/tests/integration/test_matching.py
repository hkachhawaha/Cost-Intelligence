"""Phase 2 matching integration tests (live Postgres, migration 003 applied).

Exercises the deterministic pipeline end-to-end (PO-exact + unmatched/maverick),
idempotency, the AI-confidence cap, and tenant isolation.

Run: RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_matching.py -v
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.conftest import requires_db

pytestmark = requires_db


def _dsn() -> str:
    from app.core.config import settings

    return settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")


def _admin():
    import psycopg

    return psycopg.connect(_dsn(), autocommit=True)


async def _seed(tenant_id: str):
    """Seed: tenant, one vendor with a PO contract + matching spend, and a second
    vendor with spend but no contract (→ maverick)."""
    from app.core.database import session_for_tenant
    from app.models.contract import Contract
    from app.models.spend import SpendRecord
    from app.models.tenant import Tenant
    from app.models.vendor import Vendor

    async with await session_for_tenant(tenant_id) as s:
        s.add(
            Tenant(
                id=uuid.UUID(tenant_id),
                name="Acme",
                slug=f"acme{tenant_id[:8]}",
                encryption_key_ref="kms://t",
            )
        )
        await s.flush()
        v1, v2 = uuid.uuid4(), uuid.uuid4()
        s.add(
            Vendor(
                id=v1,
                tenant_id=uuid.UUID(tenant_id),
                name="Acme",
                normalized_name="acme",
                name_fingerprint="acme",
            )
        )
        s.add(
            Vendor(
                id=v2,
                tenant_id=uuid.UUID(tenant_id),
                name="Globex",
                normalized_name="globex",
                name_fingerprint="globex",
            )
        )
        await s.flush()  # persist vendors before FK-referencing contracts/spend
        contract_id = uuid.uuid4()
        s.add(
            Contract(
                id=contract_id,
                tenant_id=uuid.UUID(tenant_id),
                vendor_id=v1,
                acv=Decimal("120000"),
                currency="USD",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                po_numbers=["PO-100"],
                status="active",
                source_system="sheets",
                source_row_hash="c1",
            )
        )
        # matched-by-PO spend
        s.add(
            SpendRecord(
                tenant_id=uuid.UUID(tenant_id),
                vendor_id=v1,
                vendor_name_raw="Acme",
                amount=Decimal("10000"),
                currency="USD",
                spend_date=date(2026, 3, 1),
                po_number="PO-100",
                source_system="sheets",
                source_row_hash="s1",
            )
        )
        # maverick spend (vendor has no contract)
        s.add(
            SpendRecord(
                tenant_id=uuid.UUID(tenant_id),
                vendor_id=v2,
                vendor_name_raw="Globex",
                amount=Decimal("5000"),
                currency="USD",
                spend_date=date(2026, 4, 1),
                po_number=None,
                source_system="sheets",
                source_row_hash="s2",
            )
        )
        await s.commit()


async def _run_match(tenant_id: str) -> dict:
    from app.core.database import session_for_tenant
    from app.services.matching import MatchingService
    from app.services.matching_candidates import CandidateRetrievalService

    async with await session_for_tenant(tenant_id) as s:
        svc = MatchingService(s, CandidateRetrievalService(s))
        counts = await svc.run_full_tenant_match(tenant_id)
        await s.commit()
        return counts


@pytest.fixture()
def tenant():
    tid = str(uuid.uuid4())
    yield tid
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "TRUNCATE tenants, vendors, contracts, spend_records, match_results, "
            "unmatched_queue, agent_runs, audit_events CASCADE"
        )
    admin.close()


async def test_matching_pipeline_po_and_maverick_idempotent(tenant):
    await _seed(tenant)
    counts = await _run_match(tenant)
    assert counts["po_exact"] == 1
    assert counts["unmatched"] == 1

    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT method, confidence FROM match_results WHERE tenant_id=%s AND method='po_exact'",
            (tenant,),
        )
        method, confidence = cur.fetchone()
        assert method == "po_exact" and float(confidence) == 1.0
        # maverick surfaced, never hidden
        cur.execute(
            "SELECT count(*) FROM unmatched_queue WHERE tenant_id=%s AND status='pending'",
            (tenant,),
        )
        assert cur.fetchone()[0] == 1
    admin.close()

    # Idempotent re-run: one match_result per spend (no duplicates).
    await _run_match(tenant)
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM match_results WHERE tenant_id=%s", (tenant,))
        assert cur.fetchone()[0] == 2
    admin.close()


async def test_ai_inference_confidence_capped(monkeypatch):
    """A model returning 0.95 must be persisted-eligible only at ≤0.80 (code cap)."""
    from types import SimpleNamespace

    from app.agents import matching as agent
    from app.services.matching import MatchingService

    cid = str(uuid.uuid4())

    async def fake_complete_json(*args, **kwargs):
        return {"contract_id": cid, "confidence": 0.95, "reasoning": "x"}

    monkeypatch.setattr(agent.model_gateway, "complete_json", fake_complete_json)

    svc = MatchingService(session=None, candidates=None)
    spend = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        vendor_id="v1",
        amount=Decimal("100"),
        spend_date=date(2026, 3, 1),
        po_number=None,
        cost_center=None,
        invoice_id=None,
        vendor_name_raw="Acme",
    )
    contract = SimpleNamespace(
        id=uuid.UUID(cid),
        vendor_id="v1",
        acv=Decimal("1200"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        po_numbers=[],
        entity_id=None,
    )
    result = await agent._ai_infer(svc, spend, [contract], "t")
    assert result is not None
    assert result.method == "ai_inferred"
    assert result.confidence <= Decimal("0.800")


def test_matching_rls_isolation(tenant):
    import asyncio

    import psycopg

    asyncio.run(_seed(tenant))
    asyncio.run(_run_match(tenant))

    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            """
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rls_app_user') THEN
                    CREATE ROLE rls_app_user LOGIN PASSWORD 'rls_test' NOSUPERUSER;
                END IF;
            END $$;
            """
        )
        cur.execute("GRANT USAGE ON SCHEMA public TO rls_app_user")
        cur.execute("GRANT SELECT ON match_results, unmatched_queue TO rls_app_user")
    admin.close()

    host = _dsn().split("://", 1)[1].split("@", 1)[1]
    conn = psycopg.connect(f"postgresql://rls_app_user:rls_test@{host}", autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (tenant,))
            cur.execute("SELECT count(*) FROM match_results")
            assert cur.fetchone()[0] == 2
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (str(uuid.uuid4()),))
            cur.execute("SELECT count(*) FROM match_results")
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()
