"""Phase 8 integration (§14.4) — live Postgres, migration 008.

The HITL rate-card verification gate (role-gated, 409 on re-verify) and the end-to-end
line-item pipeline (verified rate cards → above_rate + volume_tier detection with exact
dollars → recovery pack with per-line items). No LLM key needed.

Run: RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_line_item_pipeline.py -v
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
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
            "TRUNCATE tenants, users, vendors, contracts, invoices, invoice_line_items, "
            "match_results, opportunities, recovery_items, recovery_packs, "
            "contract_rate_cards, rate_card_tiers, agent_runs, audit_events CASCADE"
        )
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


async def _seed_base(tenant: str, user_id: str) -> dict:
    """tenant + user + vendor + contract + invoice. Returns ids."""
    from app.core.database import session_for_tenant
    from app.models.contract import Contract
    from app.models.invoice import Invoice
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.vendor import Vendor

    tid = uuid.UUID(tenant)
    vid, cid, iid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with await session_for_tenant(tenant) as s:
        s.add(Tenant(id=tid, name="Acme", slug=f"acme{tenant[:8]}", encryption_key_ref="kms://t"))
        await s.flush()
        s.add(
            User(
                id=uuid.UUID(user_id),
                tenant_id=tid,
                auth0_id=f"a|{user_id[:8]}",
                email="legal@acme.com",
            )
        )
        s.add(
            Vendor(
                id=vid,
                tenant_id=tid,
                name="CloudCo",
                normalized_name="cloudco",
                name_fingerprint="cloudco",
            )
        )
        await s.flush()
        s.add(
            Contract(
                id=cid,
                tenant_id=tid,
                vendor_id=vid,
                acv=Decimal("100000"),
                currency="USD",
                start_date=date(2025, 1, 1),
                end_date=date(2026, 12, 31),
                status="active",
                source_system="x",
                source_row_hash="c1",
            )
        )
        await s.flush()
        s.add(
            Invoice(
                id=iid,
                tenant_id=tid,
                vendor_id=vid,
                contract_id=cid,
                invoice_number="INV-1",
                invoice_date=date(2026, 3, 1),
                total_amount=Decimal("12000"),
                source_system="x",
                source_row_hash="i1",
            )
        )
        await s.commit()
    return {"vendor": str(vid), "contract": str(cid), "invoice": str(iid)}


def test_rate_card_verify_gate(tenant, monkeypatch):
    """Unverified rate card → role-gated verify (403 for wrong role); 200 for legal; 409 on
    re-verify. Only verified cards become live for $ math."""
    import asyncio as aio

    from app.core.database import session_for_tenant
    from app.models.rate_card import ContractRateCard

    user_id = str(uuid.uuid4())
    ids = aio.run(_seed_base(tenant, user_id))
    card_id = uuid.uuid4()

    async def _seed_card():
        async with await session_for_tenant(tenant) as s:
            s.add(
                ContractRateCard(
                    id=card_id,
                    tenant_id=uuid.UUID(tenant),
                    contract_id=uuid.UUID(ids["contract"]),
                    sku="CLOUD",
                    unit_rate=Decimal("0.042"),
                    source="extracted",
                    confidence=Decimal("0.9"),
                    verified_at=None,
                )
            )
            await s.commit()

    aio.run(_seed_card())

    # Wrong role → 403.
    denied = _client(tenant, user_id, "analyst", monkeypatch)
    try:
        assert denied.post(f"/api/v1/rate-cards/{card_id}/verify").status_code == 403
    finally:
        from app.main import app

        app.dependency_overrides.clear()

    # legal role → 200, then 409 on re-verify.
    client = _client(tenant, user_id, "legal", monkeypatch)
    try:
        r = client.post(f"/api/v1/rate-cards/{card_id}/verify")
        assert r.status_code == 200 and r.json()["status"] == "verified"
        assert client.post(f"/api/v1/rate-cards/{card_id}/verify").status_code == 409

        admin = _admin()
        with admin.cursor() as cur:
            cur.execute("SELECT verified_at FROM contract_rate_cards WHERE id=%s", (str(card_id),))
            assert cur.fetchone()[0] is not None
            cur.execute(
                "SELECT actor FROM audit_events WHERE event_type='rate_card.verified' "
                "AND tenant_id=%s",
                (tenant,),
            )
            assert any(a == "human" for (a,) in cur.fetchall())
        admin.close()
    finally:
        from app.main import app

        app.dependency_overrides.clear()


def test_line_item_pipeline_end_to_end(tenant, monkeypatch):
    """Verified rate cards + invoice line items → above_rate + volume_tier with exact
    dollars → recovery pack with per-line items."""
    from app.core.database import session_for_tenant
    from app.models.invoice import InvoiceLineItem
    from app.models.rate_card import ContractRateCard, RateCardTier

    user_id = str(uuid.uuid4())
    ids = asyncio.run(_seed_base(tenant, user_id))

    async def _seed_cards_and_lines():
        tid = uuid.UUID(tenant)
        cid = uuid.UUID(ids["contract"])
        iid = uuid.UUID(ids["invoice"])
        async with await session_for_tenant(tenant) as s:
            flat = ContractRateCard(
                id=uuid.uuid4(),
                tenant_id=tid,
                contract_id=cid,
                sku="CLOUD",
                unit_rate=Decimal("0.042"),
                is_tiered=False,
                source="manual",
                verified_at=datetime.now(UTC),
            )  # VERIFIED → drives math
            tiered = ContractRateCard(
                id=uuid.uuid4(),
                tenant_id=tid,
                contract_id=cid,
                sku="SEATS",
                unit_rate=Decimal("0"),
                is_tiered=True,
                source="manual",
                verified_at=datetime.now(UTC),
            )
            s.add_all([flat, tiered])
            await s.flush()
            for i, (lo, hi, rate) in enumerate([(0, 100, 120), (100, 500, 100), (500, None, 85)]):
                s.add(
                    RateCardTier(
                        id=uuid.uuid4(),
                        tenant_id=tid,
                        rate_card_id=tiered.id,
                        tier_index=i,
                        min_volume=Decimal(lo),
                        max_volume=Decimal(hi) if hi else None,
                        tier_rate=Decimal(rate),
                    )
                )
            # above_rate: CLOUD billed 0.048 vs 0.042, qty 250000 → 1500.
            s.add(
                InvoiceLineItem(
                    id=uuid.uuid4(),
                    tenant_id=tid,
                    invoice_id=iid,
                    line_number=1,
                    sku="CLOUD",
                    unit_price=Decimal("0.048"),
                    quantity=Decimal("250000"),
                )
            )
            # volume_tier: 2× SEATS qty 300 billed @ tier-1 (100); total 600 → tier-2 (85)
            # → 2 × (100-85)*300 = 9000.
            for n in (2, 3):
                s.add(
                    InvoiceLineItem(
                        id=uuid.uuid4(),
                        tenant_id=tid,
                        invoice_id=iid,
                        line_number=n,
                        sku="SEATS",
                        unit_price=Decimal("100"),
                        quantity=Decimal("300"),
                    )
                )
            await s.commit()

    asyncio.run(_seed_cards_and_lines())

    client = _client(tenant, user_id, "cfo", monkeypatch)
    try:
        r = client.post("/api/v1/detection/run-line-item")
        assert r.status_code == 202
        body = r.json()
        assert body["detected"] == 2  # above_rate + volume_tier
        assert Decimal(body["total_impact"]) == Decimal("10500")  # 1500 + 9000

        # Build the per-vendor recovery pack.
        rb = client.post(f"/api/v1/recovery/packs/build?vendor_id={ids['vendor']}")
        assert rb.status_code == 201
        pack_id = rb.json()["pack_id"]
        assert Decimal(rb.json()["total_amount"]) == Decimal("10500")

        pack = client.get(f"/api/v1/recovery/packs/{pack_id}").json()
        # 1 CLOUD line (above_rate) + 2 SEATS lines (volume_tier) = 3 per-line items.
        assert len(pack["items"]) == 3
        skus = sorted(it["sku"] for it in pack["items"] if it["sku"])
        assert skus == ["CLOUD", "SEATS", "SEATS"]
    finally:
        from app.main import app

        app.dependency_overrides.clear()
