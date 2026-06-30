"""Phase 10 — control-layer & scalability models (§4.2).

`CommitmentCheck` is an immutable advisory record of a pre-signature stress test (no delete;
sign-off appended). `PortfolioRollup` precomputes multi-entity aggregates. `TenantQuota` and
`SpendTierMetadata` back the scalability capstone (quotas/breakers, cold/warm tiering). All
tenant-scoped (RLS).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class CommitmentCheck(Base, TenantScopedMixin):
    __tablename__ = "commitment_checks"

    entity_id: Mapped[UUID | None] = mapped_column(ForeignKey("entities.id"))
    vendor_name: Mapped[str | None]
    proposed_acv: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    proposed_tcv: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    term_months: Mapped[int | None] = mapped_column(Integer)
    indexed_share: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    assumed_index_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    margin_tolerance: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    indexed_exposure: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    scenarios: Mapped[dict] = mapped_column(JSONB)
    verdict: Mapped[str] = mapped_column(String)
    conditions: Mapped[list] = mapped_column(JSONB, default=list)
    rationale: Mapped[str | None]
    advisory: Mapped[bool] = mapped_column(Boolean, default=True)
    requested_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    signed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    signed_decision: Mapped[str | None]
    signed_at: Mapped[datetime | None]


class PortfolioRollup(Base, TenantScopedMixin):
    __tablename__ = "portfolio_rollups"
    __table_args__ = (UniqueConstraint("tenant_id", "period", name="uq_portfolio_period"),)

    period: Mapped[date] = mapped_column(Date)
    total_spend: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    spend_under_mgmt_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    total_savings: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_recovery: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    by_entity: Mapped[list] = mapped_column(JSONB)
    vendor_leverage: Mapped[list] = mapped_column(JSONB, default=list)
    refreshed_at: Mapped[datetime | None]


class TenantQuota(Base, TenantScopedMixin):
    __tablename__ = "tenant_quotas"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_quota"),)

    max_spend_rows: Mapped[int] = mapped_column(BigInteger, default=10_000_000)
    max_llm_tokens_day: Mapped[int] = mapped_column(BigInteger, default=5_000_000)
    max_concurrent_syncs: Mapped[int] = mapped_column(Integer, default=2)
    max_query_qps: Mapped[int] = mapped_column(Integer, default=50)
    breaker_open: Mapped[bool] = mapped_column(Boolean, default=False)
    breaker_reason: Mapped[str | None]


class SpendTierMetadata(Base, TenantScopedMixin):
    __tablename__ = "spend_tier_metadata"
    __table_args__ = (UniqueConstraint("tenant_id", "period", name="uq_tier_period"),)

    period: Mapped[date] = mapped_column(Date)
    tier: Mapped[str] = mapped_column(String, default="hot")  # hot|warm|cold
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    archived_at: Mapped[datetime | None]
