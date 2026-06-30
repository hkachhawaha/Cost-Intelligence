"""Tenant — the top of the isolation hierarchy (not itself RLS-scoped)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str]
    slug: Mapped[str] = mapped_column(String, unique=True)
    auth0_org_id: Mapped[str | None] = mapped_column(String, unique=True)
    encryption_key_ref: Mapped[str]
    plan: Mapped[str] = mapped_column(default="standard")
    status: Mapped[str] = mapped_column(default="active")
    autonomy_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    data_residency: Mapped[str] = mapped_column(default="us")
