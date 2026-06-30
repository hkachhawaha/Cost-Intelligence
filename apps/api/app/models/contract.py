"""Contract — the 95+ field contractual "should" (§7.2), grouped per §4.1.

Phase 1 ingests structured tabular data; document-derived fields (clauses, SLA
text) are nullable here and enriched by the Contract Extraction agent (Phase 7).
Unmapped source columns land in `extra` (JSONB) so nothing is lost.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ARRAY, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class Contract(Base, TenantScopedMixin):
    __tablename__ = "contracts"

    # Identity & lineage
    contract_number: Mapped[str | None]
    external_ref: Mapped[str | None]
    parent_contract_id: Mapped[UUID | None]
    contract_type: Mapped[str | None]
    title: Mapped[str | None]
    # Parties & org
    vendor_id: Mapped[UUID] = mapped_column(index=True)
    vendor_name_raw: Mapped[str | None]
    counterparty_legal_name: Mapped[str | None]
    entity_id: Mapped[UUID | None] = mapped_column(index=True)
    business_unit: Mapped[str | None]
    region: Mapped[str | None]
    contract_owner_user_id: Mapped[UUID | None]
    signatory_internal: Mapped[str | None]
    signatory_vendor: Mapped[str | None]
    # Value
    acv: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tcv: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(default="USD")
    original_acv: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    current_acv: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    one_time_fees: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    recurring_fees: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    list_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    # Term
    start_date: Mapped[date | None]
    end_date: Mapped[date | None] = mapped_column(index=True)
    effective_date: Mapped[date | None]
    signature_date: Mapped[date | None]
    term_length_months: Mapped[int | None]
    initial_term_months: Mapped[int | None]
    is_evergreen: Mapped[bool] = mapped_column(default=False)
    # Renewal
    renewal_type: Mapped[str | None]
    renewal_notice_days: Mapped[int | None]
    renewal_term_months: Mapped[int | None]
    auto_renew_count_limit: Mapped[int | None]
    renewal_deadline: Mapped[date | None]
    non_renewal_method: Mapped[str | None]
    last_renewed_on: Mapped[date | None]
    # Escalation / indexation
    uplift_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    uplift_cap_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    uplift_floor_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    index_type: Mapped[str | None]
    indexed_share: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    index_review_month: Mapped[int | None]
    escalation_frequency: Mapped[str | None]
    base_index_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    # Commercial
    pricing_model: Mapped[str | None]
    billing_frequency: Mapped[str | None]
    billing_in_advance: Mapped[bool | None]
    true_up_terms: Mapped[str | None]
    overage_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    # Commitments & volume
    minimum_commitment: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    yearly_commit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    committed_units: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    committed_unit_type: Mapped[str | None]
    ramp_schedule: Mapped[dict | None] = mapped_column(JSONB)
    consumed_to_date: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    # Billing & payment
    payment_term_days: Mapped[int | None]
    payment_method: Mapped[str | None]
    early_payment_discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    late_fee_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    po_required: Mapped[bool | None]
    po_numbers: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    billing_contact_email: Mapped[str | None]
    gl_code_default: Mapped[str | None]
    cost_center_default: Mapped[str | None]
    # Classification & taxonomy
    category_l1: Mapped[str | None]
    category_l2: Mapped[str | None]
    category_l3: Mapped[str | None]
    spend_type: Mapped[str | None]
    is_saas: Mapped[bool | None]
    is_strategic_supplier: Mapped[bool | None]
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    # Risk & compliance
    termination_for_convenience: Mapped[bool | None]
    termination_notice_days: Mapped[int | None]
    early_termination_penalty: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    liability_cap: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    liability_cap_basis: Mapped[str | None]
    indemnification: Mapped[bool | None]
    data_processing_addendum: Mapped[bool | None]
    sla_present: Mapped[bool | None]
    sla_credit_terms: Mapped[str | None]
    governing_law: Mapped[str | None]
    confidentiality_term_months: Mapped[int | None]
    assignment_allowed: Mapped[bool | None]
    # Governance & lifecycle
    status: Mapped[str] = mapped_column(default="active")
    lifecycle_stage: Mapped[str | None]
    approval_status: Mapped[str | None]
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Source & audit
    document_url: Mapped[str | None]
    source_system: Mapped[str]
    source_id: Mapped[UUID | None]
    source_row_hash: Mapped[str]
    ingestion_batch_id: Mapped[UUID | None]
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class ContractLineItem(Base, TenantScopedMixin):
    __tablename__ = "contract_line_items"

    contract_id: Mapped[UUID] = mapped_column(index=True)
    sku: Mapped[str | None]
    description: Mapped[str | None]
    unit_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(default="USD")
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    uom: Mapped[str | None]


class ContractClause(Base, TenantScopedMixin):
    __tablename__ = "contract_clauses"

    contract_id: Mapped[UUID] = mapped_column(index=True)
    clause_type: Mapped[str]
    raw_text: Mapped[str | None]
    extracted_value: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
