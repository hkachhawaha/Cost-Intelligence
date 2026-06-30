"""Phase 7 — Advanced module/agent API schemas (§6)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

# ── Vendors ───────────────────────────────────────────────────────────────────


class VendorRollupOut(BaseModel):
    vendor_id: str
    name: str
    total_spend: Decimal
    total_acv: Decimal
    contract_count: int
    matched_spend_pct: Decimal


class VendorListResponse(BaseModel):
    vendors: list[VendorRollupOut]


class ConsolidationCandidateOut(BaseModel):
    scope: str
    key: str
    label: str
    vendor_count: int
    contract_count: int
    total_spend: Decimal
    fragmentation_score: Decimal
    rationale: dict


class ConsolidationResponse(BaseModel):
    candidates: list[ConsolidationCandidateOut]


# ── Indexation ──────────────────────────────────────────────────────────────


class ExposureLineOut(BaseModel):
    contract_id: str
    vendor_name: str
    acv: Decimal
    index_type: str
    indexed_share: Decimal
    indexed_exposure: Decimal
    formula: str


class ExposureResponse(BaseModel):
    assumed_move_pct: Decimal
    total_indexed_exposure: Decimal
    note: str = "Modeled from a first-party assumed index move; not an external benchmark."
    lines: list[ExposureLineOut]


class IndexRegisterPut(BaseModel):
    index_type: Literal["CPI", "COLA", "fixed", "custom"]
    indexed_share: Decimal  # 0..1
    notes: str | None = None


# ── Portfolio ─────────────────────────────────────────────────────────────────


class EntityRollupOut(BaseModel):
    entity_id: str
    entity_name: str
    total_spend: Decimal
    spend_under_management_pct: Decimal
    identified_savings: Decimal
    identified_recovery: Decimal


class PortfolioResponse(BaseModel):
    entities: list[EntityRollupOut]


# ── Extraction verification ───────────────────────────────────────────────────


class ExtractionItemOut(BaseModel):
    id: str
    contract_id: str | None
    status: str
    extracted_fields: dict
    extracted_clauses: list
    field_confidence: dict
    injection_flags: list
    source_document: str


class ExtractionListResponse(BaseModel):
    items: list[ExtractionItemOut]


class VerifyRequest(BaseModel):
    action: Literal["promote", "reject"]
    edited_fields: dict | None = None


# ── Anomalies ─────────────────────────────────────────────────────────────────


class AnomalyOut(BaseModel):
    id: str
    anomaly_type: str
    subject_type: str
    subject_id: str
    method: str
    score: Decimal | None
    status: str
    detail: dict


class AnomalyListResponse(BaseModel):
    anomalies: list[AnomalyOut]


class AnomalyReviewRequest(BaseModel):
    action: Literal["dismiss", "promote_to_opportunity"]


# ── Data Steward ──────────────────────────────────────────────────────────────


class ProposalOut(BaseModel):
    id: str
    proposal_type: str
    subject_type: str
    subject_id: str | None
    affects_figures: bool
    rationale: str | None
    status: str
    current_value: dict | None
    proposed_value: dict | None


class ProposalListResponse(BaseModel):
    proposals: list[ProposalOut]


class ProposalActionRequest(BaseModel):
    action: Literal["approve", "reject"]


class RunResponse(BaseModel):
    status: str
    detail: dict = {}


def _uuid(v: UUID | None) -> str | None:
    return str(v) if v else None


def _dt(v: datetime | None) -> str | None:
    return v.isoformat() if v else None
