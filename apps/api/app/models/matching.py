"""MatchResult + UnmatchedQueue — the evidentiary backbone of spend↔contract links (§7.2, §8.2).

`MatchResult.contract_id IS NULL` ⇒ unmatched (maverick). Confidence, method,
discrepancies, match_chain and score_breakdown make every link auditable and
let downstream opportunities (Phase 3) inherit the match's confidence.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class MatchResult(Base, TenantScopedMixin):
    __tablename__ = "match_results"

    spend_id: Mapped[UUID] = mapped_column(ForeignKey("spend_records.id"), index=True)
    contract_id: Mapped[UUID | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    invoice_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoices.id"))

    method: Mapped[str] = mapped_column(String, index=True)
    scenario: Mapped[int] = mapped_column(SmallInteger, default=1)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), index=True)
    status: Mapped[str] = mapped_column(String, default="accepted", index=True)

    discrepancies: Mapped[dict] = mapped_column(JSONB, default=dict)
    match_chain: Mapped[dict] = mapped_column(JSONB, default=dict)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)

    matched_by: Mapped[str] = mapped_column(String, default="system")
    human_override_reason: Mapped[str | None] = mapped_column(String, default=None)
    agent_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "spend_id", name="uq_match_results_spend"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "method IN ('po_exact','vendor_amount_date','ai_inferred','unmatched')",
            name="method_valid",
        ),
        CheckConstraint(
            "(method = 'unmatched' AND contract_id IS NULL) OR "
            "(method <> 'unmatched' AND contract_id IS NOT NULL)",
            name="unmatched_has_no_contract",
        ),
        CheckConstraint(
            "method <> 'ai_inferred' OR confidence <= 0.800",
            name="ai_confidence_capped",
        ),
        Index(
            "ix_match_results_review",
            "tenant_id",
            postgresql_where=text("status = 'needs_review'"),
        ),
    )


class UnmatchedQueue(Base, TenantScopedMixin):
    __tablename__ = "unmatched_queue"

    spend_id: Mapped[UUID] = mapped_column(ForeignKey("spend_records.id"), index=True)
    match_result_id: Mapped[UUID | None] = mapped_column(ForeignKey("match_results.id"))
    vendor_id: Mapped[UUID | None] = mapped_column(ForeignKey("vendors.id"), index=True)
    vendor_name: Mapped[str]
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(default="USD")
    spend_date: Mapped[date]
    po_number: Mapped[str | None]
    reason: Mapped[str]
    best_candidate_id: Mapped[UUID | None] = mapped_column(ForeignKey("contracts.id"))
    best_candidate_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    status: Mapped[str] = mapped_column(default="pending", index=True)
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None]

    __table_args__ = (
        UniqueConstraint("tenant_id", "spend_id", name="uq_unmatched_spend"),
        CheckConstraint(
            "status IN ('pending','reviewed','matched','accepted_maverick')",
            name="unmatched_status_valid",
        ),
        CheckConstraint(
            "reason IN ('no_po_match','no_candidate','below_threshold','ai_no_candidate')",
            name="unmatched_reason_valid",
        ),
    )
