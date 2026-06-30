"""Phase 8 — contract rate cards + volume tiers.

`ContractRateCard` is the contracted "should pay" unit rate per (contract, SKU); tiered
cards carry `RateCardTier` bands instead of a flat `unit_rate`. Only verified cards
(`verified_at IS NOT NULL`) drive $ math — the HITL gate behind line-item recovery.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin


class ContractRateCard(Base, TenantScopedMixin):
    __tablename__ = "contract_rate_cards"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "contract_id", "sku", "effective_from", name="uq_ratecard_contract_sku"
        ),
    )

    contract_id: Mapped[UUID] = mapped_column(ForeignKey("contracts.id"), index=True)
    sku: Mapped[str] = mapped_column(String, index=True)  # canonical
    raw_sku: Mapped[str | None]
    description: Mapped[str | None]
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    uom: Mapped[str] = mapped_column(String, default="each")
    currency: Mapped[str] = mapped_column(String, default="USD")
    effective_from: Mapped[date | None]
    effective_to: Mapped[date | None]
    is_tiered: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String, default="extracted")  # extracted|manual|connector
    extraction_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None]
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))

    tiers: Mapped[list[RateCardTier]] = relationship(
        back_populates="rate_card",
        cascade="all, delete-orphan",
        order_by="RateCardTier.tier_index",
    )


class RateCardTier(Base, TenantScopedMixin):
    __tablename__ = "rate_card_tiers"
    __table_args__ = (UniqueConstraint("rate_card_id", "tier_index", name="uq_tier_card_index"),)

    rate_card_id: Mapped[UUID] = mapped_column(
        ForeignKey("contract_rate_cards.id", ondelete="CASCADE"), index=True
    )
    tier_index: Mapped[int] = mapped_column(Integer)
    min_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4))  # inclusive lower bound
    max_volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))  # exclusive; NULL = ∞
    tier_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))

    rate_card: Mapped[ContractRateCard] = relationship(back_populates="tiers")
