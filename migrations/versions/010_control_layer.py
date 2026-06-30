"""Control layer & scalability — commitment checks, portfolio rollups, tenant quotas,
spend tier metadata (Phase 10)

Depends on 009. Fail-closed RLS (NULLIF) + FORCE on all four tables; commitment_checks is
no-delete (immutable advisory record — sign-off is an UPDATE that appends signature fields).

NOTE: the spec's online conversion of `spend_records` to a declaratively partitioned table
(§4.1, §10.1) is intentionally NOT performed here — it is a destructive, data-movement online
migration that must be run as a dedicated maintenance operation. `PartitionManager` (§10.1)
generates the partition DDL; `spend_tier_metadata` tracks hot/warm/cold tiering bookkeeping.

Revision ID: 010
Revises: 009
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ["commitment_checks", "portfolio_rollups", "tenant_quotas", "spend_tier_metadata"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE commitment_checks (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id          UUID NOT NULL REFERENCES tenants(id),
            entity_id          UUID REFERENCES entities(id),
            vendor_name        TEXT,
            proposed_acv       NUMERIC(18,2) NOT NULL,
            proposed_tcv       NUMERIC(18,2),
            term_months        INT,
            indexed_share      NUMERIC(5,4) NOT NULL,
            assumed_index_pct  NUMERIC(6,4) NOT NULL,
            margin_tolerance   NUMERIC(18,2) NOT NULL,
            indexed_exposure   NUMERIC(18,2) NOT NULL,
            scenarios          JSONB NOT NULL,
            verdict            TEXT NOT NULL,
            conditions         JSONB NOT NULL DEFAULT '[]',
            rationale          TEXT,
            advisory           BOOLEAN NOT NULL DEFAULT TRUE,
            requested_by       UUID REFERENCES users(id),
            signed_by          UUID REFERENCES users(id),
            signed_decision    TEXT,
            signed_at          TIMESTAMPTZ,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_commitment_tenant ON commitment_checks (tenant_id, created_at)")

    op.execute(
        """
        CREATE TABLE portfolio_rollups (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id            UUID NOT NULL REFERENCES tenants(id),
            period               DATE NOT NULL,
            total_spend          NUMERIC(18,2) NOT NULL,
            spend_under_mgmt_pct NUMERIC(5,2) NOT NULL,
            total_savings        NUMERIC(18,2) NOT NULL,
            total_recovery       NUMERIC(18,2) NOT NULL,
            by_entity            JSONB NOT NULL,
            vendor_leverage      JSONB NOT NULL DEFAULT '[]',
            refreshed_at         TIMESTAMPTZ,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_portfolio_period UNIQUE (tenant_id, period)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE tenant_quotas (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id            UUID NOT NULL REFERENCES tenants(id),
            max_spend_rows       BIGINT NOT NULL DEFAULT 10000000,
            max_llm_tokens_day   BIGINT NOT NULL DEFAULT 5000000,
            max_concurrent_syncs INT NOT NULL DEFAULT 2,
            max_query_qps        INT NOT NULL DEFAULT 50,
            breaker_open         BOOLEAN NOT NULL DEFAULT FALSE,
            breaker_reason       TEXT,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_tenant_quota UNIQUE (tenant_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE spend_tier_metadata (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            period      DATE NOT NULL,
            tier        TEXT NOT NULL DEFAULT 'hot',
            row_count   BIGINT NOT NULL DEFAULT 0,
            archived_at TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_tier_period UNIQUE (tenant_id, period)
        )
        """
    )

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

    # Immutable advisory record (no delete; sign-off is an UPDATE that appends signature fields).
    op.execute(
        "CREATE RULE commitment_checks_no_delete AS ON DELETE TO commitment_checks DO INSTEAD NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP RULE IF EXISTS commitment_checks_no_delete ON commitment_checks")
    for t in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
