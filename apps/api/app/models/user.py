"""User — tenant-scoped; auth0_id bridges to the identity provider."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class User(Base, TenantScopedMixin):
    __tablename__ = "users"

    auth0_id: Mapped[str] = mapped_column(String, unique=True)
    email: Mapped[str]
    full_name: Mapped[str | None]
    role_id: Mapped[UUID | None] = mapped_column(index=True)
    entity_id: Mapped[UUID | None] = mapped_column(index=True)  # ABAC scope
    status: Mapped[str] = mapped_column(default="active")
    last_login_at: Mapped[datetime | None]
