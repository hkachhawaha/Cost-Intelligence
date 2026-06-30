"""Cost Intelligence storage (single workspace — NOT tenant-scoped, no RLS).

`CiDataSource` holds the connected Google Sheet config + sync status. `CiMemorySnapshot` is the
versioned Agent Memory: one JSONB document per build holding the normalized dataset,
relationships, opportunities and KPIs. The app and NirvanAI read the latest snapshot — never
the live sheet — until a Refresh writes a new version.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CiDataSource(Base, TimestampMixin):
    __tablename__ = "ci_data_source"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    spreadsheet_id: Mapped[str] = mapped_column(String, unique=True)
    spreadsheet_url: Mapped[str]
    spreadsheet_name: Mapped[str | None]
    status: Mapped[str] = mapped_column(String, default="never")  # never|connected|error
    last_synced_at: Mapped[datetime | None]
    total_records: Mapped[int] = mapped_column(BigInteger, default=0)
    last_error: Mapped[str | None]


class CiMemorySnapshot(Base, TimestampMixin):
    __tablename__ = "ci_memory_snapshot"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
