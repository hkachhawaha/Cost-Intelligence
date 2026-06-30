"""Opportunity + RecoveryItem — detected, quantified, trackable findings (§7.2).

`impact` is always code-computed; `rationale` is LLM-written and must never alter
the figure. Dedup via partial unique indexes on (tenant, type, contract_id).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class Opportunity(Base, TenantScopedMixin):
    __tablename__ = "opportunities"

    contract_id: Mapped[UUID | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    vendor_id: Mapped[UUID | None] = mapped_column(ForeignKey("vendors.id"), index=True)
    type: Mapped[str]
    bucket: Mapped[str]
    impact: Mapped[Decimal] = mapped_column(Numeric(18, 2))  # never LLM
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    rank_score: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0, index=True)
    time_sensitivity: Mapped[int] = mapped_column(SmallInteger, default=0)
    effort: Mapped[int] = mapped_column(SmallInteger, default=50)
    status: Mapped[str] = mapped_column(String, default="detected", index=True)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    rationale: Mapped[str | None]  # LLM-written, cited
    recommended_template: Mapped[str | None]
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    realized_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    dismiss_reason: Mapped[str | None]
    agent_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))
    detected_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    # Phase 8 — header/line-item coexistence (dedup so the same dollars count once).
    granularity: Mapped[str] = mapped_column(String, default="header")  # header|line_item
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    superseded_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    counts_in_total: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="opp_confidence_range"),
        CheckConstraint("impact >= 0", name="opp_impact_nonneg"),
        CheckConstraint(
            "type IN ('maverick','unused_commitment','overspend','auto_renewal',"
            "'uplift_creep','post_expiry','duplicate_invoice','missing_invoice',"
            "'above_rate','volume_tier')",
            name="opp_type_valid",
        ),
        CheckConstraint("bucket IN ('savings','recovery','control')", name="opp_bucket_valid"),
        CheckConstraint(
            "status IN ('detected','triaged','in_progress','realized','dismissed',"
            "'requires_rate_card_data')",
            name="opp_status_valid",
        ),
        CheckConstraint(
            "status <> 'dismissed' OR dismiss_reason IS NOT NULL", name="opp_dismiss_reason"
        ),
        # Header dedup only — line-item opps (granularity='line_item') intentionally
        # coexist per invoice/SKU and are not covered by this unique index.
        Index(
            "uq_opp_type_contract",
            "tenant_id",
            "type",
            "contract_id",
            unique=True,
            postgresql_where=text("contract_id IS NOT NULL AND granularity = 'header'"),
        ),
        Index(
            "uq_opp_type_tenantwide",
            "tenant_id",
            "type",
            unique=True,
            postgresql_where=text("contract_id IS NULL AND granularity = 'header'"),
        ),
    )


class RecoveryPack(Base, TenantScopedMixin):
    """A per-vendor bundle of recoverable items (Phase 8). Human-sent, never auto-sent."""

    __tablename__ = "recovery_packs"

    vendor_id: Mapped[UUID | None] = mapped_column(ForeignKey("vendors.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft|sent|recovered|closed
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)


class RecoveryItem(Base, TenantScopedMixin):
    __tablename__ = "recovery_items"

    opp_id: Mapped[UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    pack_id: Mapped[UUID | None] = mapped_column(ForeignKey("recovery_packs.id"), index=True)
    vendor_id: Mapped[UUID | None] = mapped_column(ForeignKey("vendors.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(default="USD")
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(default="detected", index=True)
    recovered_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    # Phase 8 — per-line-item recovery evidence.
    line_item_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoice_line_items.id"))
    sku: Mapped[str | None]
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    billed_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    contracted_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    line_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    __table_args__ = (
        CheckConstraint("amount >= 0", name="rec_amount_nonneg"),
        CheckConstraint(
            "status IN ('detected','packaged','challenged','recovered','written_off')",
            name="rec_status_valid",
        ),
    )
