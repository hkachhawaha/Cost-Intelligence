"""Phase 7 — Advanced module/agent models: extraction queue, anomaly flags,
data-steward proposals, index/COLA register.

All tenant-scoped (RLS). Extraction items and figure-affecting steward proposals are
gated: nothing enters the canonical record (or changes a reported figure) without an
explicit human action (§5.6, §14.3)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class ExtractionQueueItem(Base, TenantScopedMixin):
    """Contract-extraction verification queue — never auto-commits to canonical."""

    __tablename__ = "extraction_queue"

    contract_id: Mapped[UUID | None] = mapped_column(ForeignKey("contracts.id"))
    source_document: Mapped[str] = mapped_column(Text)
    extracted_fields: Mapped[dict] = mapped_column(JSONB)
    extracted_clauses: Mapped[list] = mapped_column(JSONB, default=list)
    extracted_rate_card: Mapped[list] = mapped_column(JSONB, default=list)
    field_confidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    injection_flags: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(
        default="needs_verification"
    )  # …|verified|rejected|promoted
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None]
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))


class AnomalyFlag(Base, TenantScopedMixin):
    """Statistical anomaly flag (Z-score/IQR/rule) — pending human review."""

    __tablename__ = "anomaly_flags"

    anomaly_type: Mapped[str]  # spend_spike|new_vendor|off_pattern_gl|duplicate_payment
    subject_type: Mapped[str]  # spend_record|vendor|invoice
    subject_id: Mapped[UUID]
    method: Mapped[str]  # zscore|iqr|rule
    score: Mapped[float | None] = mapped_column(Numeric(8, 3))  # code-computed
    detail: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        default="pending"
    )  # …|reviewed|dismissed|promoted_to_opportunity
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))


class StewardProposal(Base, TenantScopedMixin):
    """Data-quality fix proposal. Figure-affecting fixes require human approval (§14.3)."""

    __tablename__ = "steward_proposals"

    proposal_type: Mapped[str]  # merge_vendor|fix_currency|remap_gl|fill_missing|reconcile_total
    subject_type: Mapped[str]
    subject_id: Mapped[UUID | None]
    current_value: Mapped[dict | None] = mapped_column(JSONB)
    proposed_value: Mapped[dict | None] = mapped_column(JSONB)
    affects_figures: Mapped[bool] = mapped_column(Boolean, default=False)  # TRUE → human approval
    rationale: Mapped[str | None] = mapped_column(Text)  # LLM-written, no figures
    status: Mapped[str] = mapped_column(default="proposed")  # …|approved|applied|rejected
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))


class IndexRegisterEntry(Base, TenantScopedMixin):
    """Per-contract index/COLA register entry (Indexation module)."""

    __tablename__ = "index_register"

    contract_id: Mapped[UUID] = mapped_column(ForeignKey("contracts.id"), index=True)
    index_type: Mapped[str]  # CPI|COLA|fixed|custom
    indexed_share: Mapped[float] = mapped_column(Numeric(5, 4))  # 0..1
    notes: Mapped[str | None]
