"""Declarative base + shared mixins.

`Base` maps Python `UUID` annotations to Postgres native UUID columns.
`TenantScopedMixin` adds the `id` PK and the `tenant_id` discriminator that
every RLS policy keys on (the DB policy is the real enforcement; this mixin
guarantees the column + index exist).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    Maps Python `UUID` → Postgres native UUID, and `datetime` → TIMESTAMPTZ so
    timezone-aware datetimes (we always use UTC-aware) match the migrations'
    `TIMESTAMPTZ` columns — asyncpg rejects aware values bound to naive columns.
    """

    type_annotation_map = {
        UUID: PGUUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantScopedMixin(TimestampMixin):
    """Every tenant-owned table mixes this in."""

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
