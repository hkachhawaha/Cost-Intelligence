"""Line-item depth & recovery — rate cards, tiers, recovery packs, line-item columns (Phase 8)

Depends on 007. Adds contract_rate_cards / rate_card_tiers / recovery_packs (fail-closed
RLS + FORCE); extends invoice_line_items, opportunities (coexistence cols + widened
type/status CHECKs), and recovery_items (per-line evidence + pack_id). The header dedup
unique indexes are narrowed to granularity='header' so line-item opps coexist.

Revision ID: 008
Revises: 007
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ["contract_rate_cards", "rate_card_tiers", "recovery_packs"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contract_rate_cards (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id         UUID NOT NULL REFERENCES tenants(id),
            contract_id       UUID NOT NULL REFERENCES contracts(id),
            sku               TEXT NOT NULL,
            raw_sku           TEXT,
            description       TEXT,
            unit_rate         NUMERIC(18,6) NOT NULL,
            uom               TEXT NOT NULL DEFAULT 'each',
            currency          TEXT NOT NULL DEFAULT 'USD',
            effective_from    DATE,
            effective_to      DATE,
            is_tiered         BOOLEAN NOT NULL DEFAULT FALSE,
            source            TEXT NOT NULL DEFAULT 'extracted',
            extraction_run_id UUID REFERENCES agent_runs(run_id),
            verified_by       UUID REFERENCES users(id),
            verified_at       TIMESTAMPTZ,
            confidence        NUMERIC(4,3),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_ratecard_contract_sku UNIQUE (tenant_id, contract_id, sku, effective_from)
        )
        """
    )
    op.execute("CREATE INDEX ix_ratecard_contract ON contract_rate_cards (tenant_id, contract_id)")
    op.execute("CREATE INDEX ix_ratecard_sku ON contract_rate_cards (tenant_id, sku)")

    op.execute(
        """
        CREATE TABLE rate_card_tiers (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id),
            rate_card_id  UUID NOT NULL REFERENCES contract_rate_cards(id) ON DELETE CASCADE,
            tier_index    INT  NOT NULL,
            min_volume    NUMERIC(18,4) NOT NULL,
            max_volume    NUMERIC(18,4),
            tier_rate     NUMERIC(18,6) NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_tier_card_index UNIQUE (rate_card_id, tier_index),
            CONSTRAINT ck_tier_bounds CHECK (max_volume IS NULL OR max_volume > min_volume)
        )
        """
    )
    op.execute("CREATE INDEX ix_tier_card ON rate_card_tiers (tenant_id, rate_card_id)")

    op.execute(
        """
        CREATE TABLE recovery_packs (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id),
            vendor_id     UUID REFERENCES vendors(id),
            status        TEXT NOT NULL DEFAULT 'draft',
            total_amount  NUMERIC(18,2) NOT NULL DEFAULT 0,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_recovery_packs_vendor ON recovery_packs (tenant_id, vendor_id)")

    # ── invoice_line_items — populate the P1 scaffold with analysis fields ──
    op.execute("ALTER TABLE invoice_line_items ADD COLUMN line_number INTEGER")
    op.execute("ALTER TABLE invoice_line_items ADD COLUMN raw_sku TEXT")
    op.execute("ALTER TABLE invoice_line_items ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD'")
    op.execute(
        "ALTER TABLE invoice_line_items ADD COLUMN contract_id UUID REFERENCES contracts(id)"
    )
    op.execute(
        "ALTER TABLE invoice_line_items "
        "ADD COLUMN rate_card_id UUID REFERENCES contract_rate_cards(id)"
    )
    op.execute("CREATE INDEX ix_lineitem_sku ON invoice_line_items (tenant_id, sku)")
    op.execute("CREATE INDEX ix_lineitem_contract ON invoice_line_items (tenant_id, contract_id)")

    # ── opportunities — coexistence linkage + widened type/status CHECKs ──
    op.execute("ALTER TABLE opportunities ADD COLUMN granularity TEXT NOT NULL DEFAULT 'header'")
    op.execute("ALTER TABLE opportunities ADD COLUMN supersedes_id UUID REFERENCES opportunities(id)")
    op.execute(
        "ALTER TABLE opportunities ADD COLUMN superseded_by_id UUID REFERENCES opportunities(id)"
    )
    op.execute("ALTER TABLE opportunities ADD COLUMN counts_in_total BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute("ALTER TABLE opportunities DROP CONSTRAINT opp_type_valid")
    op.execute(
        "ALTER TABLE opportunities ADD CONSTRAINT opp_type_valid CHECK (type IN "
        "('maverick','unused_commitment','overspend','auto_renewal','uplift_creep',"
        "'post_expiry','duplicate_invoice','missing_invoice','above_rate','volume_tier'))"
    )
    op.execute("ALTER TABLE opportunities DROP CONSTRAINT opp_status_valid")
    op.execute(
        "ALTER TABLE opportunities ADD CONSTRAINT opp_status_valid CHECK (status IN "
        "('detected','triaged','in_progress','realized','dismissed','requires_rate_card_data'))"
    )
    # Narrow the header dedup indexes to header granularity (line-item opps coexist).
    op.execute("DROP INDEX uq_opp_type_contract")
    op.execute("DROP INDEX uq_opp_type_tenantwide")
    op.execute(
        "CREATE UNIQUE INDEX uq_opp_type_contract ON opportunities (tenant_id, type, contract_id) "
        "WHERE contract_id IS NOT NULL AND granularity = 'header'"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_opp_type_tenantwide ON opportunities (tenant_id, type) "
        "WHERE contract_id IS NULL AND granularity = 'header'"
    )

    # ── recovery_items — pack linkage + per-line evidence ──
    op.execute("ALTER TABLE recovery_items ADD COLUMN pack_id UUID REFERENCES recovery_packs(id)")
    op.execute(
        "ALTER TABLE recovery_items ADD COLUMN line_item_id UUID REFERENCES invoice_line_items(id)"
    )
    op.execute("ALTER TABLE recovery_items ADD COLUMN sku TEXT")
    op.execute("ALTER TABLE recovery_items ADD COLUMN quantity NUMERIC(18,4)")
    op.execute("ALTER TABLE recovery_items ADD COLUMN billed_rate NUMERIC(18,6)")
    op.execute("ALTER TABLE recovery_items ADD COLUMN contracted_rate NUMERIC(18,6)")
    op.execute("ALTER TABLE recovery_items ADD COLUMN line_delta NUMERIC(18,4)")
    op.execute("CREATE INDEX ix_rec_pack ON recovery_items (tenant_id, pack_id)")

    # Fail-closed RLS + FORCE on the new tables.
    for t in _RLS_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE  ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {t}
                USING      (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            """
        )


def downgrade() -> None:
    for col in ("line_delta", "contracted_rate", "billed_rate", "quantity", "sku",
                "line_item_id", "pack_id"):
        op.execute(f"ALTER TABLE recovery_items DROP COLUMN IF EXISTS {col}")
    op.execute("DROP INDEX IF EXISTS uq_opp_type_contract")
    op.execute("DROP INDEX IF EXISTS uq_opp_type_tenantwide")
    op.execute("ALTER TABLE opportunities DROP CONSTRAINT IF EXISTS opp_type_valid")
    op.execute("ALTER TABLE opportunities DROP CONSTRAINT IF EXISTS opp_status_valid")
    op.execute(
        "ALTER TABLE opportunities ADD CONSTRAINT opp_type_valid CHECK (type IN "
        "('maverick','unused_commitment','overspend','auto_renewal','uplift_creep',"
        "'post_expiry','duplicate_invoice','missing_invoice'))"
    )
    op.execute(
        "ALTER TABLE opportunities ADD CONSTRAINT opp_status_valid CHECK (status IN "
        "('detected','triaged','in_progress','realized','dismissed'))"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_opp_type_contract ON opportunities (tenant_id, type, contract_id) "
        "WHERE contract_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_opp_type_tenantwide ON opportunities (tenant_id, type) "
        "WHERE contract_id IS NULL"
    )
    for col in ("granularity", "supersedes_id", "superseded_by_id", "counts_in_total"):
        op.execute(f"ALTER TABLE opportunities DROP COLUMN IF EXISTS {col}")
    for col in ("line_number", "raw_sku", "currency", "contract_id", "rate_card_id"):
        op.execute(f"ALTER TABLE invoice_line_items DROP COLUMN IF EXISTS {col}")
    for t in reversed(_RLS_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
