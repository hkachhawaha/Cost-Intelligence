"""Phase 8 — line-item ingestion + rate-card data contracts (§4.3)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, field_validator


class InboundInvoiceLineItem(BaseModel):
    invoice_number: str
    line_number: int
    sku: str | None = None
    description: str | None = None
    unit_price: Decimal
    quantity: Decimal
    uom: str = "each"
    currency: str = "USD"

    @field_validator("quantity", "unit_price")
    @classmethod
    def non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


class RateCardTierSpec(BaseModel):
    min_volume: Decimal
    max_volume: Decimal | None = None
    tier_rate: Decimal


class ExtractedRateCardEntry(BaseModel):
    sku: str
    description: str | None = None
    unit_rate: Decimal | None = None  # None when tiered
    uom: str = "each"
    is_tiered: bool = False
    tiers: list[RateCardTierSpec] = []
    confidence: Decimal

    @field_validator("tiers")
    @classmethod
    def tiers_required_when_tiered(cls, v, info):
        if info.data.get("is_tiered") and not v:
            raise ValueError("tiered rate card must include tiers")
        return v
