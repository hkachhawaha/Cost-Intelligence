from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class OpportunityOut(BaseModel):
    id: UUID
    contract_id: UUID | None
    vendor_id: UUID | None
    type: str
    bucket: Literal["savings", "recovery", "control"]
    impact: Decimal
    confidence: Decimal
    rank_score: Decimal
    time_sensitivity: int
    effort: int
    status: Literal["detected", "triaged", "in_progress", "realized", "dismissed"]
    owner_id: UUID | None
    rationale: str | None
    recommended_template: str | None
    detected_at: datetime


class OpportunityDetail(OpportunityOut):
    evidence: dict


class OpportunityList(BaseModel):
    items: list[OpportunityOut]
    total: int
    page: int
    page_size: int
    totals: dict


class StatusPatch(BaseModel):
    status: Literal["triaged", "in_progress", "realized", "dismissed"]
    dismiss_reason: str | None = Field(default=None, max_length=500)
    realized_amount: Decimal | None = None


class AssignPatch(BaseModel):
    owner_id: UUID
