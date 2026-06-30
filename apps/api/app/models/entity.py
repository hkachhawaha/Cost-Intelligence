"""Entity — legal entity / business unit. Tenant-scoped, hierarchical."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class Entity(Base, TenantScopedMixin):
    __tablename__ = "entities"

    name: Mapped[str]
    type: Mapped[str]  # 'legal_entity' | 'business_unit'
    external_ref: Mapped[str | None]
    parent_entity_id: Mapped[UUID | None] = mapped_column(index=True)
