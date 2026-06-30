"""matching — match_results + unmatched_queue (Phase 2)

Depends on 002 (vendors, contracts, spend_records, invoices). Fail-closed RLS
(NULLIF) + FORCE, matching the Phase 0/1 convention. updated_at is handled by
the ORM `onupdate` (consistent with prior migrations — no DB trigger needed).

Revision ID: 003
Revises: 002
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ["match_results", "unmatched_queue"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE match_results (
            id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id             UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            spend_id              UUID NOT NULL REFERENCES spend_records(id),
            contract_id           UUID REFERENCES contracts(id),
            invoice_id            UUID REFERENCES invoices(id),
            method                TEXT NOT NULL,
            scenario              SMALLINT NOT NULL DEFAULT 1,
            confidence            NUMERIC(4,3) NOT NULL,
            status                TEXT NOT NULL DEFAULT 'accepted',
            discrepancies         JSONB NOT NULL DEFAULT '{}'::jsonb,
            match_chain           JSONB NOT NULL DEFAULT '{}'::jsonb,
            score_breakdown       JSONB NOT NULL DEFAULT '{}'::jsonb,
            matched_by            TEXT NOT NULL DEFAULT 'system',
            human_override_reason TEXT,
            agent_run_id          UUID REFERENCES agent_runs(run_id),
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT confidence_range CHECK (confidence >= 0 AND confidence <= 1),
            CONSTRAINT method_valid CHECK (method IN
                ('po_exact','vendor_amount_date','ai_inferred','unmatched')),
            CONSTRAINT status_valid CHECK (status IN
                ('accepted','spot_check','needs_review','unmatched','reassigned')),
            CONSTRAINT unmatched_has_no_contract CHECK (
                (method = 'unmatched' AND contract_id IS NULL) OR
                (method <> 'unmatched' AND contract_id IS NOT NULL)),
            CONSTRAINT ai_confidence_capped CHECK (
                method <> 'ai_inferred' OR confidence <= 0.800)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX uq_match_results_spend ON match_results (tenant_id, spend_id)")
    op.execute("CREATE INDEX ix_match_results_contract ON match_results (tenant_id, contract_id)")
    op.execute("CREATE INDEX ix_match_results_confidence ON match_results (tenant_id, confidence)")
    op.execute("CREATE INDEX ix_match_results_method ON match_results (tenant_id, method)")
    op.execute("CREATE INDEX ix_match_results_status ON match_results (tenant_id, status)")
    op.execute(
        "CREATE INDEX ix_match_results_review ON match_results (tenant_id) "
        "WHERE status = 'needs_review'"
    )

    op.execute(
        """
        CREATE TABLE unmatched_queue (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id            UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            spend_id             UUID NOT NULL REFERENCES spend_records(id),
            match_result_id      UUID REFERENCES match_results(id),
            vendor_id            UUID REFERENCES vendors(id),
            vendor_name          TEXT NOT NULL,
            amount               NUMERIC(18,2) NOT NULL,
            currency             TEXT NOT NULL DEFAULT 'USD',
            spend_date           DATE NOT NULL,
            po_number            TEXT,
            reason               TEXT NOT NULL,
            best_candidate_id    UUID REFERENCES contracts(id),
            best_candidate_score NUMERIC(4,3),
            status               TEXT NOT NULL DEFAULT 'pending',
            resolved_by          UUID REFERENCES users(id),
            resolved_at          TIMESTAMPTZ,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_unmatched_spend UNIQUE (tenant_id, spend_id),
            CONSTRAINT unmatched_status_valid CHECK (status IN
                ('pending','reviewed','matched','accepted_maverick')),
            CONSTRAINT unmatched_reason_valid CHECK (reason IN
                ('no_po_match','no_candidate','below_threshold','ai_no_candidate'))
        )
        """
    )
    op.execute("CREATE INDEX ix_unmatched_status ON unmatched_queue (tenant_id, status)")
    op.execute("CREATE INDEX ix_unmatched_vendor ON unmatched_queue (tenant_id, vendor_id)")

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
