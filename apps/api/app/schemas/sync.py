from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SyncStartRequest(BaseModel):
    source_id: str


class SyncStartResponse(BaseModel):
    sync_run_id: str
    task_id: str | None
    kind: Literal["initial", "refresh"]
    status: Literal["running"]


class CoverageStats(BaseModel):
    match_coverage_pct: Decimal
    spend_under_management_pct: Decimal
    contract_count: int
    opportunity_count: int


class SyncStatusResponse(BaseModel):
    initialized: bool
    status: Literal["running", "completed", "failed", "partial"] | None
    stage: str | None
    stale: bool
    last_synced_at: datetime | None
    memory_version: int | None
    coverage: CoverageStats | None
    error_message: str | None


class AgentRunOut(BaseModel):
    run_id: UUID
    agent: str
    trigger: str
    status: str
    actor: str
    confidence: Decimal | None
    inputs_ref: str | None
    outputs_ref: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


class AgentRunListResponse(BaseModel):
    items: list[AgentRunOut]
    total: int
    page: int
    page_size: int
