"""Vendor — canonical supplier; folds name variants together (§7.3)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class Vendor(Base, TenantScopedMixin):
    __tablename__ = "vendors"

    name: Mapped[str]  # canonical display name
    normalized_name: Mapped[str]  # cleaned form
    name_fingerprint: Mapped[str] = mapped_column(index=True)  # dedup key
    tax_id: Mapped[str | None]
    duns: Mapped[str | None]


class VendorAlias(Base, TenantScopedMixin):
    __tablename__ = "vendor_aliases"

    vendor_id: Mapped[UUID] = mapped_column(index=True)
    raw_name: Mapped[str]
    source: Mapped[str]  # which feed introduced this alias
