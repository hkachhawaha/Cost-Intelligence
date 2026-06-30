"""Advanced modules & agents — extraction queue, anomaly flags, steward proposals,
index register, spend enrichment columns (Phase 7)

Depends on 006. Fail-closed RLS (NULLIF) + FORCE on the four new tenant tables; adds
the Enrichment output columns to spend_records.

Revision ID: 007
Revises: 006
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ["extraction_queue", "anomaly_flags", "steward_proposals", "index_register"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE extraction_queue (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id),
            contract_id         UUID REFERENCES contracts(id),
            source_document     TEXT NOT NULL,
            extracted_fields    JSONB NOT NULL,
            extracted_clauses   JSONB NOT NULL DEFAULT '[]',
            extracted_rate_card JSONB NOT NULL DEFAULT '[]',
            field_confidence    JSONB NOT NULL DEFAULT '{}',
            injection_flags     JSONB NOT NULL DEFAULT '[]',
            status              TEXT NOT NULL DEFAULT 'needs_verification',
            verified_by         UUID REFERENCES users(id),
            verified_at         TIMESTAMPTZ,
            run_id              UUID REFERENCES agent_runs(run_id),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_extraction_queue_status ON extraction_queue (tenant_id, status)")

    op.execute(
        """
        CREATE TABLE anomaly_flags (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id),
            anomaly_type  TEXT NOT NULL,
            subject_type  TEXT NOT NULL,
            subject_id    UUID NOT NULL,
            method        TEXT NOT NULL,
            score         NUMERIC(8,3),
            detail        JSONB NOT NULL,
            status        TEXT NOT NULL DEFAULT 'pending',
            reviewed_by   UUID REFERENCES users(id),
            run_id        UUID REFERENCES agent_runs(run_id),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_anomaly_flags_status ON anomaly_flags (tenant_id, status, anomaly_type)"
    )

    op.execute(
        """
        CREATE TABLE steward_proposals (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            proposal_type   TEXT NOT NULL,
            subject_type    TEXT NOT NULL,
            subject_id      UUID,
            current_value   JSONB,
            proposed_value  JSONB,
            affects_figures BOOLEAN NOT NULL DEFAULT FALSE,
            rationale       TEXT,
            status          TEXT NOT NULL DEFAULT 'proposed',
            approved_by     UUID REFERENCES users(id),
            run_id          UUID REFERENCES agent_runs(run_id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_steward_proposals_status ON steward_proposals (tenant_id, status)")

    op.execute(
        """
        CREATE TABLE index_register (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id),
            contract_id   UUID NOT NULL REFERENCES contracts(id),
            index_type    TEXT NOT NULL,
            indexed_share NUMERIC(5,4) NOT NULL,
            notes         TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_index_register_contract ON index_register (tenant_id, contract_id)")

    # Enrichment output columns on spend_records.
    op.execute("ALTER TABLE spend_records ADD COLUMN taxonomy_l1 TEXT")
    op.execute("ALTER TABLE spend_records ADD COLUMN taxonomy_l2 TEXT")
    op.execute("ALTER TABLE spend_records ADD COLUMN base_amount NUMERIC(18,2)")
    op.execute("ALTER TABLE spend_records ADD COLUMN fx_rate NUMERIC(18,6)")
    op.execute("ALTER TABLE spend_records ADD COLUMN enrichment_confidence NUMERIC(4,3)")

    # Fail-closed RLS + FORCE on every new table (consistent with prior phases).
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
    for col in ("enrichment_confidence", "fx_rate", "base_amount", "taxonomy_l2", "taxonomy_l1"):
        op.execute(f"ALTER TABLE spend_records DROP COLUMN IF EXISTS {col}")
    for t in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
