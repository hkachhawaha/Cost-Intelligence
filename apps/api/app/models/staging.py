"""DataSource, IngestionBatch, StagedRecord (quarantine buffer)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class DataSource(Base, TenantScopedMixin):
    __tablename__ = "data_sources"

    name: Mapped[str]
    source_type: Mapped[str]
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    credentials_secret: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="pending")
    last_synced_at: Mapped[datetime | None]
    last_error: Mapped[str | None]


class IngestionBatch(Base, TenantScopedMixin):
    __tablename__ = "ingestion_batches"

    source_id: Mapped[UUID]
    run_id: Mapped[UUID | None]
    dataset_type: Mapped[str]
    status: Mapped[str] = mapped_column(default="running")
    record_count: Mapped[int] = mapped_column(default=0)
    inserted_count: Mapped[int] = mapped_column(default=0)
    updated_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]


class StagedRecord(Base, TenantScopedMixin):
    __tablename__ = "staged_records"

    source_id: Mapped[UUID]
    batch_id: Mapped[UUID | None]
    record_type: Mapped[str]
    raw_data: Mapped[dict] = mapped_column(JSONB)
    validation_errors: Mapped[list] = mapped_column(JSONB, default=list)
    source_row_hash: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")
    resolved_by: Mapped[UUID | None]
    resolved_at: Mapped[datetime | None]
