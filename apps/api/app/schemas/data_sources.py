from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ColumnMappingIn(BaseModel):
    source_header: str
    canonical_field: str


class CreateDataSourceRequest(BaseModel):
    name: str
    source_type: str = "google_sheets"
    spreadsheet_id: str
    ranges: dict[str, str] | None = None
    column_mappings: dict[str, list[ColumnMappingIn]] = Field(default_factory=dict)


class DataSourceResponse(BaseModel):
    id: UUID
    name: str
    source_type: str
    status: str
    last_synced_at: datetime | None
    last_error: str | None
    oauth_url: str | None = None


class RefreshResponse(BaseModel):
    task_id: str
    status: str = "queued"


class IngestionBatchResponse(BaseModel):
    id: UUID
    dataset_type: str
    status: str
    record_count: int
    inserted_count: int
    updated_count: int
    error_count: int
    started_at: datetime
    completed_at: datetime | None


class QuarantineItem(BaseModel):
    id: UUID
    record_type: str
    raw_data: dict
    validation_errors: list[dict]
    status: str
    created_at: datetime


class ResolveQuarantineRequest(BaseModel):
    action: str  # 'promote' | 'discard' | 'fix'
    patch: dict | None = None
