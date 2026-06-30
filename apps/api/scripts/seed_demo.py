#!/usr/bin/env python
"""Seed a demo tenant and run the full pipeline so the local UI has data to click through.

Creates one tenant (= settings.dev_tenant_id, matched by the dev auth bypass), two legal
entities, three vendors, contracts/invoices/spend engineered to trigger real opportunities,
then runs matching → detection → memory build, and opens one Phase-9 approval task. Idempotent:
TRUNCATEs the demo tables first (local dev DB only).

Run from the repo root (so .env is loaded):

    DEV_AUTH_BYPASS=true uv run --project apps/api python apps/api/scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # put apps/api on sys.path

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402

DEMO_TENANT = settings.dev_tenant_id
DEMO_USER = settings.dev_user_id

# Wiped (CASCADE) on each run so the seed is idempotent — local demo DB only.
_WIPE = (
    "tenants, users, entities, vendors, vendor_aliases, contracts, invoices, "
    "invoice_line_items, spend_records, match_results, unmatched_queue, opportunities, "
    "recovery_items, recovery_packs, contract_rate_cards, rate_card_tiers, tasks, "
    "approval_gates, task_reminders, commitment_checks, portfolio_rollups, tenant_quotas, "
    "spend_tier_metadata, tenant_memory, sync_runs, agent_runs, audit_events"
)


def _wipe() -> None:
    import psycopg

    dsn = settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(f"TRUNCATE {_WIPE} CASCADE")  # TRUNCATE is not subject to RLS row policies
    print("• wiped demo tables")


async def _seed_canonical() -> dict:
    from app.core.database import session_for_tenant
    from app.models.contract import Contract
    from app.models.entity import Entity
    from app.models.invoice import Invoice
    from app.models.rate_card import ContractRateCard
    from app.models.spend import SpendRecord
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.vendor import Vendor

    tid = UUID(DEMO_TENANT)
    today = date.today()
    e_us, e_eu = uuid4(), uuid4()
    v_cloud, v_data, v_office = uuid4(), uuid4(), uuid4()
    c1, c2, c3 = uuid4(), uuid4(), uuid4()

    async with await session_for_tenant(DEMO_TENANT) as s:
        s.add(Tenant(id=tid, name="Demo Co", slug="demo", encryption_key_ref="kms://demo"))
        await s.flush()
        s.add(User(id=UUID(DEMO_USER), tenant_id=tid, auth0_id="dev|demo",
                   email="dev@terzo.local", full_name="Dev User", entity_id=e_us))
        s.add_all([
            Entity(id=e_us, tenant_id=tid, name="Acme US", type="legal_entity"),
            Entity(id=e_eu, tenant_id=tid, name="Acme EU", type="legal_entity"),
            Vendor(id=v_cloud, tenant_id=tid, name="CloudCo", normalized_name="cloudco",
                   name_fingerprint="cloudco"),
            Vendor(id=v_data, tenant_id=tid, name="DataCorp", normalized_name="datacorp",
                   name_fingerprint="datacorp"),
            Vendor(id=v_office, tenant_id=tid, name="OfficeMax", normalized_name="officemax",
                   name_fingerprint="officemax"),
        ])
        await s.flush()

        # C1 — CloudCo/US: auto-renew INSIDE the notice window (end soon) + 7% uplift +
        # overspend (matched spend > ACV). Triggers auto_renewal, uplift_creep, overspend.
        s.add(Contract(
            id=c1, tenant_id=tid, vendor_id=v_cloud, entity_id=e_us, title="CloudCo Platform",
            acv=Decimal("240000"), currency="USD",
            start_date=today - timedelta(days=345), end_date=today + timedelta(days=20),
            renewal_type="auto", renewal_notice_days=30, uplift_pct=Decimal("0.07"),
            indexed_share=Decimal("0.60"), index_type="CPI", yearly_commit=Decimal("240000"),
            status="active", source_system="seed", source_row_hash="c1", po_numbers=["PO-1001"],
        ))
        # C2 — DataCorp/EU: 5% uplift only. Triggers uplift_creep.
        s.add(Contract(
            id=c2, tenant_id=tid, vendor_id=v_data, entity_id=e_eu, title="DataCorp Analytics",
            acv=Decimal("120000"), currency="USD",
            start_date=today - timedelta(days=120), end_date=today + timedelta(days=240),
            renewal_type="none", uplift_pct=Decimal("0.05"), yearly_commit=Decimal("120000"),
            status="active", source_system="seed", source_row_hash="c2", po_numbers=["PO-2001"],
        ))
        # C3 — CloudCo/EU: makes CloudCo span TWO entities → portfolio leverage candidate.
        s.add(Contract(
            id=c3, tenant_id=tid, vendor_id=v_cloud, entity_id=e_eu, title="CloudCo EU",
            acv=Decimal("80000"), currency="USD",
            start_date=today - timedelta(days=60), end_date=today + timedelta(days=300),
            renewal_type="none", status="active", source_system="seed",
            source_row_hash="c3", po_numbers=["PO-3001"],
        ))
        await s.flush()

        # Invoices (one per contract).
        for n, (vid, cid) in enumerate([(v_cloud, c1), (v_data, c2), (v_cloud, c3)], start=1):
            s.add(Invoice(
                id=uuid4(), tenant_id=tid, vendor_id=vid, contract_id=cid,
                invoice_number=f"INV-{n:03d}", invoice_date=today - timedelta(days=15),
                total_amount=Decimal("10000"), source_system="seed", source_row_hash=f"inv{n}",
            ))

        # Spend. PO-tagged rows match to contracts (po_exact); the OfficeMax rows have no PO
        # and no contract → unmatched → maverick.
        def spend(vid, eid, amt, po, n, days_ago=10):
            return SpendRecord(
                id=uuid4(), tenant_id=tid, vendor_id=vid, entity_id=eid, amount=Decimal(amt),
                currency="USD", spend_date=today - timedelta(days=days_ago), po_number=po,
                source_system="seed", source_row_hash=f"sp{n}",
            )

        rows = [
            spend(v_cloud, e_us, "100000", "PO-1001", 1),  # C1 matched: 3×100k = 300k > 240k ACV
            spend(v_cloud, e_us, "100000", "PO-1001", 2),
            spend(v_cloud, e_us, "100000", "PO-1001", 3),
            spend(v_data, e_eu, "90000", "PO-2001", 4),    # C2 matched, under ACV
            spend(v_cloud, e_eu, "80000", "PO-3001", 5),   # C3 matched (CloudCo in EU)
            spend(v_office, e_us, "50000", None, 6),       # maverick (no PO)
            spend(v_office, e_us, "30000", None, 7),       # maverick
        ]
        s.add_all(rows)

        # An unverified rate card → shows in the rate-card verification queue (Phase 8).
        s.add(ContractRateCard(
            id=uuid4(), tenant_id=tid, contract_id=c1, sku="CLOUD-COMPUTE",
            unit_rate=Decimal("0.042"), source="extracted", confidence=Decimal("0.88"),
            verified_at=None,
        ))
        await s.commit()
    return {"contract_auto_renewal": str(c1)}


async def _run_pipeline() -> dict:
    from app.core.database import session_for_tenant
    from app.core.kpi_cache import RedisKpiCache
    from app.core.redis import get_redis
    from app.services.detection import DetectionService
    from app.services.matching import MatchingService
    from app.services.matching_candidates import CandidateRetrievalService
    from app.services.memory import MemoryService
    from app.services.memory_kpis import KpiComputer
    from app.services.scoring import ScoringService

    async with await session_for_tenant(DEMO_TENANT) as s:
        counts = await MatchingService(s, CandidateRetrievalService(s)).run_full_tenant_match(
            DEMO_TENANT
        )
        await s.commit()

    async with await session_for_tenant(DEMO_TENANT) as s:
        opps = await DetectionService(s, ScoringService()).run_all_rules(DEMO_TENANT)
        await s.commit()

    async with await session_for_tenant(DEMO_TENANT) as s:
        snap = await MemoryService(s, RedisKpiCache(get_redis()), KpiComputer(s)).build(
            DEMO_TENANT
        )
        total_identified = str(snap.total_identified)
    return {"match_counts": counts, "opportunities": len(opps),
            "total_identified": total_identified}


async def _open_workflow_task() -> str | None:
    """Open one Phase-9 approval task for the auto-renewal opportunity (awaiting_approval)."""
    from app.core.database import session_for_tenant
    from app.models.opportunity import Opportunity
    from app.services.workflow import WorkflowService

    async with await session_for_tenant(DEMO_TENANT) as s:
        opp = await s.scalar(
            select(Opportunity).where(Opportunity.type == "auto_renewal").limit(1)
        )
        if opp is None:
            return None
        deadline = (date.today() + timedelta(days=20)).isoformat()
        out = await WorkflowService(s, DEMO_TENANT).run_for_opportunity(
            opportunity_id=str(opp.id), opportunity_type="auto_renewal",
            confidence=float(opp.confidence), deadline=deadline,
        )
        await s.commit()
        return out.get("task_id")


async def _amain() -> None:
    ids = await _seed_canonical()
    print(f"• seeded canonical data (auto-renewal contract {ids['contract_auto_renewal'][:8]}…)")
    pipeline = await _run_pipeline()
    print(f"• matching: {pipeline['match_counts']}")
    print(f"• detection: {pipeline['opportunities']} opportunities "
          f"(${pipeline['total_identified']} identified)")
    task_id = await _open_workflow_task()
    print(f"• workflow task awaiting approval: {task_id}")


def main() -> None:
    if settings.is_production:
        sys.exit("refusing to seed: ENVIRONMENT is prod")
    if "--no-wipe" not in sys.argv:
        _wipe()
    asyncio.run(_amain())
    print(f"\n✓ demo tenant seeded: {DEMO_TENANT}")
    print("  Start the API with DEV_AUTH_BYPASS=true and the web app with "
          "NEXT_PUBLIC_DEV_AUTH=1, then open http://localhost:3000")


if __name__ == "__main__":
    main()
