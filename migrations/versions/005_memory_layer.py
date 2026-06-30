"""memory layer — tenant_memory, contract_embeddings, sync_runs (Phase 4)

Depends on 004. Fail-closed RLS (NULLIF) + FORCE. pgvector `vector` extension was
created in migration 001. IVFFlat ANN index on the embedding column. updated_at
handled by the ORM onupdate (consistent with prior migrations).

Revision ID: 005
Revises: 004
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ["tenant_memory", "contract_embeddings", "sync_runs"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE tenant_memory (
            tenant_id                   UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            last_synced_at              TIMESTAMPTZ NOT NULL,
            stale                       BOOLEAN NOT NULL DEFAULT FALSE,
            memory_version              INTEGER NOT NULL DEFAULT 1,
            build_run_id                UUID REFERENCES agent_runs(run_id),
            source_fingerprint          TEXT,
            total_spend                 NUMERIC(18,2) NOT NULL DEFAULT 0,
            spend_under_management_pct  NUMERIC(5,2)  NOT NULL DEFAULT 0,
            contract_compliance_pct     NUMERIC(5,2)  NOT NULL DEFAULT 0,
            po_coverage_pct             NUMERIC(5,2)  NOT NULL DEFAULT 0,
            match_coverage_pct          NUMERIC(5,2)  NOT NULL DEFAULT 0,
            total_savings               NUMERIC(18,2) NOT NULL DEFAULT 0,
            total_recovery              NUMERIC(18,2) NOT NULL DEFAULT 0,
            total_identified            NUMERIC(18,2) NOT NULL DEFAULT 0,
            total_realized              NUMERIC(18,2) NOT NULL DEFAULT 0,
            opportunity_count           INTEGER NOT NULL DEFAULT 0,
            contract_count              INTEGER NOT NULL DEFAULT 0,
            vendor_count                INTEGER NOT NULL DEFAULT 0,
            spend_record_count          INTEGER NOT NULL DEFAULT 0,
            opportunity_count_by_type   JSONB NOT NULL DEFAULT '{}'::jsonb,
            opportunity_amount_by_type  JSONB NOT NULL DEFAULT '{}'::jsonb,
            top_opportunities           JSONB NOT NULL DEFAULT '[]'::jsonb,
            vendor_summary              JSONB NOT NULL DEFAULT '[]'::jsonb,
            renewal_calendar            JSONB NOT NULL DEFAULT '{}'::jsonb,
            spend_by_category           JSONB NOT NULL DEFAULT '[]'::jsonb,
            spend_by_cost_center        JSONB NOT NULL DEFAULT '[]'::jsonb,
            spend_trend                 JSONB NOT NULL DEFAULT '[]'::jsonb,
            match_coverage_breakdown    JSONB NOT NULL DEFAULT '{}'::jsonb,
            data_quality_summary        JSONB NOT NULL DEFAULT '{}'::jsonb,
            alerts                      JSONB NOT NULL DEFAULT '[]'::jsonb,
            kpi_snapshot                JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE contract_embeddings (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            contract_id    UUID NOT NULL REFERENCES contracts(id),
            clause_id      UUID REFERENCES contract_clauses(id),
            chunk_index    INTEGER NOT NULL,
            chunk_text     TEXT NOT NULL,
            chunk_type     TEXT NOT NULL DEFAULT 'contract',
            token_count    INTEGER,
            embedding      VECTOR(1536) NOT NULL,
            model          TEXT NOT NULL DEFAULT 'gemini-embedding-001',
            memory_version INTEGER NOT NULL DEFAULT 1,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_contract_embeddings UNIQUE (tenant_id, contract_id, chunk_index, memory_version)
        )
        """
    )
    op.execute("CREATE INDEX idx_contract_embeddings_contract ON contract_embeddings (tenant_id, contract_id)")
    op.execute(
        "CREATE INDEX idx_contract_embeddings_ann ON contract_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.execute(
        """
        CREATE TABLE sync_runs (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            source_id      UUID NOT NULL,
            kind           TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'running',
            celery_task_id TEXT,
            stage          TEXT,
            error_message  TEXT,
            started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at   TIMESTAMPTZ,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT sync_runs_status_chk CHECK (status IN ('running','completed','failed','partial'))
        )
        """
    )
    op.execute("CREATE INDEX idx_sync_runs_tenant_started ON sync_runs (tenant_id, started_at DESC)")

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
