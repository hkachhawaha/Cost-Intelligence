"""SpendRecord — what actually happened (§7.2). contract_id set later (Phase 2)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class SpendRecord(Base, TenantScopedMixin):
    __tablename__ = "spend_records"

    vendor_id: Mapped[UUID] = mapped_column(index=True)
    vendor_name_raw: Mapped[str | None]
    contract_id: Mapped[UUID | None] = mapped_column(index=True)  # set by Matching (Phase 2)
    invoice_id: Mapped[UUID | None]
    entity_id: Mapped[UUID | None]
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(default="USD")
    spend_date: Mapped[date] = mapped_column(index=True)
    gl_code: Mapped[str | None]
    cost_center: Mapped[str | None]
    po_number: Mapped[str | None] = mapped_column(index=True)  # primary match key
    description: Mapped[str | None]
    source_system: Mapped[str]
    source_id: Mapped[UUID | None]
    source_row_hash: Mapped[str]
    ingestion_batch_id: Mapped[UUID | None]
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Enrichment outputs (Phase 7) — set by the Enrichment agent.
    taxonomy_l1: Mapped[str | None]  # top-level category
    taxonomy_l2: Mapped[str | None]  # sub-category
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))  # normalized to base ccy
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))  # first-party rate used
    enrichment_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
