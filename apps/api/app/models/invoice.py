"""Invoice + InvoiceLineItem (line items scaffolded; populated Phase 8)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class Invoice(Base, TenantScopedMixin):
    __tablename__ = "invoices"

    vendor_id: Mapped[UUID] = mapped_column(index=True)
    vendor_name_raw: Mapped[str | None]
    contract_id: Mapped[UUID | None]
    invoice_number: Mapped[str] = mapped_column(index=True)
    invoice_date: Mapped[date]
    due_date: Mapped[date | None]
    payment_date: Mapped[date | None]
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(default="USD")
    status: Mapped[str] = mapped_column(default="open")
    po_number: Mapped[str | None]
    gl_code: Mapped[str | None]
    cost_center: Mapped[str | None]
    source_system: Mapped[str]
    source_id: Mapped[UUID | None]
    source_row_hash: Mapped[str]
    ingestion_batch_id: Mapped[UUID | None]
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class InvoiceLineItem(Base, TenantScopedMixin):
    __tablename__ = "invoice_line_items"

    invoice_id: Mapped[UUID] = mapped_column(index=True)
    line_number: Mapped[int | None]
    sku: Mapped[str | None] = mapped_column(index=True)  # canonical
    raw_sku: Mapped[str | None]  # SKU as on the invoice
    description: Mapped[str | None]
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    uom: Mapped[str | None]
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(default="USD")
    # Phase 8 — line→contract/rate-card linkage (inherited from match).
    contract_id: Mapped[UUID | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    rate_card_id: Mapped[UUID | None] = mapped_column(ForeignKey("contract_rate_cards.id"))
