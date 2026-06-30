"""ingestion schema — data_sources, vendors, contracts (95 fields), spend, invoices, staging

Phase 1: the canonical contract/spend/invoice model + connector bookkeeping +
quarantine buffer, all tenant-scoped with fail-closed RLS (NULLIF, matching the
Phase 0 correction). FKs to tenants CASCADE here (these are operational tables,
not the append-only audit log).

Revision ID: 002
Revises: 001
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "data_sources", "vendors", "vendor_aliases", "contracts",
    "contract_line_items", "contract_clauses", "spend_records", "invoices",
    "invoice_line_items", "ingestion_batches", "staged_records",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE data_sources (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id          UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name               TEXT NOT NULL,
            source_type        TEXT NOT NULL,
            config             JSONB NOT NULL DEFAULT '{}'::jsonb,
            credentials_secret TEXT,
            status             TEXT NOT NULL DEFAULT 'pending',
            last_synced_at     TIMESTAMPTZ,
            last_error         TEXT,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT data_sources_type_chk CHECK (source_type IN ('google_sheets','csv','excel','coupa','oracle','sap')),
            CONSTRAINT data_sources_status_chk CHECK (status IN ('pending','connected','error','disabled'))
        )
        """
    )
    op.execute("CREATE INDEX ix_data_sources_tenant ON data_sources (tenant_id)")

    op.execute(
        """
        CREATE TABLE vendors (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            normalized_name  TEXT NOT NULL,
            name_fingerprint TEXT NOT NULL,
            tax_id           TEXT,
            duns             TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_vendors_tenant ON vendors (tenant_id)")
    op.execute("CREATE INDEX ix_vendors_fingerprint ON vendors (tenant_id, name_fingerprint)")
    op.execute("CREATE INDEX ix_vendors_trgm ON vendors USING gin (normalized_name gin_trgm_ops)")

    op.execute(
        """
        CREATE TABLE vendor_aliases (
            id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id  UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            vendor_id  UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
            raw_name   TEXT NOT NULL,
            source     TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_vendor_aliases_vendor ON vendor_aliases (vendor_id)")
    op.execute("CREATE UNIQUE INDEX uq_vendor_aliases_tenant_raw ON vendor_aliases (tenant_id, lower(raw_name))")

    op.execute(
        """
        CREATE TABLE contracts (
            id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id                   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            contract_number             TEXT,
            external_ref                TEXT,
            parent_contract_id          UUID REFERENCES contracts(id),
            contract_type               TEXT,
            title                       TEXT,
            vendor_id                   UUID NOT NULL REFERENCES vendors(id),
            vendor_name_raw             TEXT,
            counterparty_legal_name     TEXT,
            entity_id                   UUID REFERENCES entities(id),
            business_unit               TEXT,
            region                      TEXT,
            contract_owner_user_id      UUID REFERENCES users(id),
            signatory_internal          TEXT,
            signatory_vendor            TEXT,
            acv                         NUMERIC(18,2),
            tcv                         NUMERIC(18,2),
            currency                    TEXT NOT NULL DEFAULT 'USD',
            original_acv                NUMERIC(18,2),
            current_acv                 NUMERIC(18,2),
            one_time_fees               NUMERIC(18,2),
            recurring_fees              NUMERIC(18,2),
            discount_pct                NUMERIC(6,4),
            list_value                  NUMERIC(18,2),
            start_date                  DATE,
            end_date                    DATE,
            effective_date              DATE,
            signature_date              DATE,
            term_length_months          INT,
            initial_term_months         INT,
            is_evergreen                BOOLEAN NOT NULL DEFAULT false,
            renewal_type                TEXT,
            renewal_notice_days         INT,
            renewal_term_months         INT,
            auto_renew_count_limit      INT,
            renewal_deadline            DATE,
            non_renewal_method          TEXT,
            last_renewed_on             DATE,
            uplift_pct                  NUMERIC(6,4),
            uplift_cap_pct              NUMERIC(6,4),
            uplift_floor_pct            NUMERIC(6,4),
            index_type                  TEXT,
            indexed_share               NUMERIC(6,4),
            index_review_month          INT,
            escalation_frequency        TEXT,
            base_index_value            NUMERIC(12,4),
            pricing_model               TEXT,
            billing_frequency           TEXT,
            billing_in_advance          BOOLEAN,
            true_up_terms               TEXT,
            overage_rate                NUMERIC(18,4),
            minimum_commitment          NUMERIC(18,2),
            yearly_commit               NUMERIC(18,2),
            committed_units             NUMERIC(18,4),
            committed_unit_type         TEXT,
            ramp_schedule               JSONB,
            consumed_to_date            NUMERIC(18,4),
            payment_term_days           INT,
            payment_method              TEXT,
            early_payment_discount_pct  NUMERIC(6,4),
            late_fee_pct                NUMERIC(6,4),
            po_required                 BOOLEAN,
            po_numbers                  TEXT[] NOT NULL DEFAULT '{}',
            billing_contact_email       TEXT,
            gl_code_default             TEXT,
            cost_center_default         TEXT,
            category_l1                 TEXT,
            category_l2                 TEXT,
            category_l3                 TEXT,
            spend_type                  TEXT,
            is_saas                     BOOLEAN,
            is_strategic_supplier       BOOLEAN,
            tags                        TEXT[] NOT NULL DEFAULT '{}',
            termination_for_convenience BOOLEAN,
            termination_notice_days     INT,
            early_termination_penalty   NUMERIC(18,2),
            liability_cap               NUMERIC(18,2),
            liability_cap_basis         TEXT,
            indemnification             BOOLEAN,
            data_processing_addendum    BOOLEAN,
            sla_present                 BOOLEAN,
            sla_credit_terms            TEXT,
            governing_law               TEXT,
            confidentiality_term_months INT,
            assignment_allowed          BOOLEAN,
            status                      TEXT NOT NULL DEFAULT 'active',
            lifecycle_stage             TEXT,
            approval_status             TEXT,
            risk_score                  NUMERIC(5,2),
            document_url                TEXT,
            source_system               TEXT NOT NULL,
            source_id                   UUID REFERENCES data_sources(id),
            source_row_hash             TEXT NOT NULL,
            ingestion_batch_id          UUID,
            extra                       JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT contracts_renewal_type_chk CHECK (renewal_type IS NULL OR renewal_type IN ('auto','option','none')),
            CONSTRAINT contracts_status_chk CHECK (status IN ('draft','active','expired','terminated','renewed')),
            CONSTRAINT contracts_term_chk CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
            CONSTRAINT contracts_acv_chk CHECK (acv IS NULL OR acv >= 0),
            CONSTRAINT contracts_indexed_share_chk CHECK (indexed_share IS NULL OR (indexed_share >= 0 AND indexed_share <= 1))
        )
        """
    )
    op.execute("CREATE INDEX ix_contracts_tenant ON contracts (tenant_id)")
    op.execute("CREATE INDEX ix_contracts_vendor ON contracts (tenant_id, vendor_id)")
    op.execute("CREATE INDEX ix_contracts_entity ON contracts (tenant_id, entity_id)")
    op.execute("CREATE INDEX ix_contracts_enddate ON contracts (tenant_id, end_date)")
    op.execute("CREATE INDEX ix_contracts_po ON contracts USING gin (po_numbers)")
    op.execute("CREATE UNIQUE INDEX uq_contracts_source_row ON contracts (tenant_id, source_id, source_row_hash)")

    op.execute(
        """
        CREATE TABLE contract_line_items (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            contract_id  UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
            sku          TEXT,
            description  TEXT,
            unit_rate    NUMERIC(18,4),
            currency     TEXT NOT NULL DEFAULT 'USD',
            quantity     NUMERIC(18,4),
            uom          TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_contract_line_items_contract ON contract_line_items (contract_id)")

    op.execute(
        """
        CREATE TABLE contract_clauses (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            contract_id     UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
            clause_type     TEXT NOT NULL,
            raw_text        TEXT,
            extracted_value JSONB NOT NULL DEFAULT '{}'::jsonb,
            confidence      NUMERIC(4,3),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_contract_clauses_contract ON contract_clauses (contract_id)")

    op.execute(
        """
        CREATE TABLE spend_records (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id          UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            vendor_id          UUID NOT NULL REFERENCES vendors(id),
            vendor_name_raw    TEXT,
            contract_id        UUID REFERENCES contracts(id),
            invoice_id         UUID,
            entity_id          UUID REFERENCES entities(id),
            amount             NUMERIC(18,2) NOT NULL,
            currency           TEXT NOT NULL DEFAULT 'USD',
            spend_date         DATE NOT NULL,
            gl_code            TEXT,
            cost_center        TEXT,
            po_number          TEXT,
            description        TEXT,
            source_system      TEXT NOT NULL,
            source_id          UUID REFERENCES data_sources(id),
            source_row_hash    TEXT NOT NULL,
            ingestion_batch_id UUID,
            extra              JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT spend_amount_chk CHECK (amount >= 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_spend_tenant ON spend_records (tenant_id)")
    op.execute("CREATE INDEX ix_spend_vendor ON spend_records (tenant_id, vendor_id)")
    op.execute("CREATE INDEX ix_spend_contract ON spend_records (tenant_id, contract_id)")
    op.execute("CREATE INDEX ix_spend_date ON spend_records (tenant_id, spend_date)")
    op.execute("CREATE INDEX ix_spend_po ON spend_records (tenant_id, po_number)")
    op.execute("CREATE UNIQUE INDEX uq_spend_source_row ON spend_records (tenant_id, source_id, source_row_hash)")

    op.execute(
        """
        CREATE TABLE invoices (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id          UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            vendor_id          UUID NOT NULL REFERENCES vendors(id),
            vendor_name_raw    TEXT,
            contract_id        UUID REFERENCES contracts(id),
            invoice_number     TEXT NOT NULL,
            invoice_date       DATE NOT NULL,
            due_date           DATE,
            payment_date       DATE,
            total_amount       NUMERIC(18,2) NOT NULL,
            currency           TEXT NOT NULL DEFAULT 'USD',
            status             TEXT NOT NULL DEFAULT 'open',
            po_number          TEXT,
            gl_code            TEXT,
            cost_center        TEXT,
            source_system      TEXT NOT NULL,
            source_id          UUID REFERENCES data_sources(id),
            source_row_hash    TEXT NOT NULL,
            ingestion_batch_id UUID,
            extra              JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT invoices_status_chk CHECK (status IN ('paid','open','overdue')),
            CONSTRAINT invoices_amount_chk CHECK (total_amount >= 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_invoices_tenant ON invoices (tenant_id)")
    op.execute("CREATE INDEX ix_invoices_vendor ON invoices (tenant_id, vendor_id)")
    op.execute("CREATE INDEX ix_invoices_number ON invoices (tenant_id, invoice_number)")
    op.execute("CREATE INDEX ix_invoices_po ON invoices (tenant_id, po_number)")
    op.execute("CREATE UNIQUE INDEX uq_invoices_source_row ON invoices (tenant_id, source_id, source_row_hash)")

    op.execute(
        """
        CREATE TABLE invoice_line_items (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            invoice_id  UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            sku         TEXT,
            description TEXT,
            unit_price  NUMERIC(18,4),
            quantity    NUMERIC(18,4),
            uom         TEXT,
            line_total  NUMERIC(18,2),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_invoice_line_items_invoice ON invoice_line_items (invoice_id)")

    op.execute(
        """
        CREATE TABLE ingestion_batches (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            source_id      UUID NOT NULL REFERENCES data_sources(id),
            run_id         UUID REFERENCES agent_runs(run_id),
            dataset_type   TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'running',
            record_count   INT NOT NULL DEFAULT 0,
            inserted_count INT NOT NULL DEFAULT 0,
            updated_count  INT NOT NULL DEFAULT 0,
            error_count    INT NOT NULL DEFAULT 0,
            started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at   TIMESTAMPTZ,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ingestion_batches_status_chk CHECK (status IN ('running','completed','failed'))
        )
        """
    )
    op.execute("CREATE INDEX ix_ingestion_batches_source ON ingestion_batches (tenant_id, source_id, started_at DESC)")

    op.execute(
        """
        CREATE TABLE staged_records (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            source_id         UUID NOT NULL REFERENCES data_sources(id),
            batch_id          UUID REFERENCES ingestion_batches(id),
            record_type       TEXT NOT NULL,
            raw_data          JSONB NOT NULL,
            validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_row_hash   TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'pending',
            resolved_by       UUID REFERENCES users(id),
            resolved_at       TIMESTAMPTZ,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT staged_status_chk CHECK (status IN ('pending','promoted','discarded','fixed'))
        )
        """
    )
    op.execute("CREATE INDEX ix_staged_tenant ON staged_records (tenant_id, status)")
    op.execute("CREATE INDEX ix_staged_batch ON staged_records (batch_id)")

    # RLS on every tenant-scoped table (fail-closed NULLIF, matching Phase 0).
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
