from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class MatchResultOut(BaseModel):
    id: UUID
    spend_id: UUID
    contract_id: UUID | None
    invoice_id: UUID | None
    method: Literal["po_exact", "vendor_amount_date", "ai_inferred", "unmatched"]
    scenario: int
    confidence: Decimal
    status: Literal["accepted", "spot_check", "needs_review", "unmatched", "reassigned"]
    discrepancies: dict
    match_chain: dict
    score_breakdown: dict
    matched_by: Literal["system", "human"]
    human_override_reason: str | None
    created_at: datetime


class MatchResultList(BaseModel):
    items: list[MatchResultOut]
    total: int
    page: int
    page_size: int


class AcceptMatchRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ReassignMatchRequest(BaseModel):
    contract_id: UUID | None = None  # None ⇒ accept as maverick
    reason: str = Field(min_length=3, max_length=500)


class RematchRequest(BaseModel):
    scope: Literal["unmatched", "low_confidence", "all"] = "unmatched"


class RematchResponse(BaseModel):
    task_id: str
    scope: str


class UnmatchedOut(BaseModel):
    id: UUID
    spend_id: UUID
    vendor_name: str
    amount: Decimal
    currency: str
    spend_date: date
    po_number: str | None
    reason: str
    best_candidate_id: UUID | None
    best_candidate_score: Decimal | None
    status: str
