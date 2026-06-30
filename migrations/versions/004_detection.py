"""detection — opportunities + recovery_items (Phase 3)

Depends on 003 (match_results). Fail-closed RLS (NULLIF) + FORCE; partial unique
indexes dedup live opportunities by (type, contract_id) and (type) tenant-wide.
updated_at handled by the ORM onupdate (consistent with prior migrations).

Revision ID: 004
Revises: 003
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ["opportunities", "recovery_items"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE opportunities (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            contract_id     UUID REFERENCES contracts(id),
            vendor_id       UUID REFERENCES vendors(id),
            type            TEXT NOT NULL,
            bucket          TEXT NOT NULL,
            impact          NUMERIC(18,2) NOT NULL,
            confidence      NUMERIC(4,3) NOT NULL,
            rank_score      NUMERIC(20,4) NOT NULL DEFAULT 0,
            time_sensitivity SMALLINT NOT NULL DEFAULT 0,
            effort          SMALLINT NOT NULL DEFAULT 50,
            status          TEXT NOT NULL DEFAULT 'detected',
            owner_id        UUID REFERENCES users(id),
            rationale       TEXT,
            recommended_template TEXT,
            evidence        JSONB NOT NULL DEFAULT '{}'::jsonb,
            realized_amount NUMERIC(18,2),
            dismiss_reason  TEXT,
            agent_run_id    UUID REFERENCES agent_runs(run_id),
            detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT opp_confidence_range CHECK (confidence >= 0 AND confidence <= 1),
            CONSTRAINT opp_impact_nonneg CHECK (impact >= 0),
            CONSTRAINT opp_type_valid CHECK (type IN
                ('maverick','unused_commitment','overspend','auto_renewal','uplift_creep',
                 'post_expiry','duplicate_invoice','missing_invoice')),
            CONSTRAINT opp_bucket_valid CHECK (bucket IN ('savings','recovery','control')),
            CONSTRAINT opp_status_valid CHECK (status IN
                ('detected','triaged','in_progress','realized','dismissed')),
            CONSTRAINT opp_dismiss_reason CHECK (status <> 'dismissed' OR dismiss_reason IS NOT NULL)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_opp_type_contract ON opportunities (tenant_id, type, contract_id) "
        "WHERE contract_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_opp_type_tenantwide ON opportunities (tenant_id, type) "
        "WHERE contract_id IS NULL"
    )
    op.execute("CREATE INDEX ix_opp_rank ON opportunities (tenant_id, rank_score DESC)")
    op.execute("CREATE INDEX ix_opp_status ON opportunities (tenant_id, status)")
    op.execute("CREATE INDEX ix_opp_bucket ON opportunities (tenant_id, bucket)")
    op.execute("CREATE INDEX ix_opp_owner ON opportunities (tenant_id, owner_id)")
    op.execute("CREATE INDEX ix_opp_vendor ON opportunities (tenant_id, vendor_id)")

    op.execute(
        """
        CREATE TABLE recovery_items (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            opp_id      UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            vendor_id   UUID REFERENCES vendors(id),
            amount      NUMERIC(18,2) NOT NULL,
            currency    TEXT NOT NULL DEFAULT 'USD',
            evidence    JSONB NOT NULL DEFAULT '{}'::jsonb,
            status      TEXT NOT NULL DEFAULT 'detected',
            recovered_amount NUMERIC(18,2),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT rec_amount_nonneg CHECK (amount >= 0),
            CONSTRAINT rec_status_valid CHECK (status IN
                ('detected','packaged','challenged','recovered','written_off'))
        )
        """
    )
    op.execute("CREATE INDEX ix_rec_opp ON recovery_items (tenant_id, opp_id)")
    op.execute("CREATE INDEX ix_rec_vendor ON recovery_items (tenant_id, vendor_id)")
    op.execute("CREATE INDEX ix_rec_status ON recovery_items (tenant_id, status)")

    for t in _TABLES:
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
    for t in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
