"""Phase 5 read-model response schemas (§4.2).

UI-facing shapes over the Phase-4 memory layer + canonical drill-downs. Money is
already pre-computed upstream (Decimal, §5.6); these schemas only carry it.

Hardening vs. the spec: fields that can legitimately be absent for a brand-new
tenant (uninitialized memory) or a sparsely-populated contract are given defaults
or made nullable so a read never 500s on incomplete data — the UI branches on
`initialized`/`has_indexation` instead.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class DashboardKpis(BaseModel):
    initialized: bool = False
    stale: bool = False
    last_synced_at: str | None = None
    memory_version: int | None = None
    total_spend: Decimal = Decimal("0")
    spend_under_management_pct: Decimal = Decimal("0")
    contract_compliance_pct: Decimal = Decimal("0")
    po_coverage_pct: Decimal = Decimal("0")
    match_coverage_pct: Decimal = Decimal("0")
    total_savings: Decimal = Decimal("0")
    total_recovery: Decimal = Decimal("0")
    total_identified: Decimal = Decimal("0")
    opportunity_count_by_type: dict[str, int] = {}
    opportunity_amount_by_type: dict[str, str] = {}
    top_opportunities: list[dict] = []
    alerts: list[dict] = []


class SpendBreakdownItem(BaseModel):
    label: str
    amount: Decimal


class SpendBreakdownResponse(BaseModel):
    dimension: str
    items: list[SpendBreakdownItem]


class SpendTrendPoint(BaseModel):
    month: str
    amount: Decimal


class SpendTrendResponse(BaseModel):
    items: list[SpendTrendPoint]


class MatchCoverageResponse(BaseModel):
    po_exact: int = 0
    vendor_amount_date: int = 0
    ai_inferred: int = 0
    unmatched: int = 0
    coverage_pct: Decimal = Decimal("0")


class ContractSummary(BaseModel):
    id: str
    vendor_id: str
    acv: Decimal | None = None
    tcv: Decimal | None = None
    start_date: str | None = None
    end_date: str | None = None
    renewal_type: str | None = None
    status: str
    indexation: dict


class ContractListResponse(BaseModel):
    items: list[ContractSummary]
    total: int
    page: int
    page_size: int


class ContractDetail(ContractSummary):
    effective_date: str | None = None
    renewal_notice_days: int | None = None
    uplift_pct: Decimal = Decimal("0")
    yearly_commit: Decimal = Decimal("0")
    payment_term_days: int | None = None
    currency: str
    po_numbers: list[str] = []
    source_system: str


class ContractSpendLine(BaseModel):
    spend_id: str
    amount: Decimal
    spend_date: str
    po_number: str | None = None


class ContractSpendResponse(BaseModel):
    contract_id: str
    total_matched_spend: Decimal
    utilization_pct: Decimal
    lines: list[ContractSpendLine]


class RenewalEntry(BaseModel):
    contract_id: str
    vendor_id: str
    end_date: str
    days_to_end: int
    renewal_type: str | None = None
    notice_deadline: str
    acv: Decimal | None = None


class RenewalsResponse(BaseModel):
    within_90: list[RenewalEntry] = []
    within_180: list[RenewalEntry] = []
    within_365: list[RenewalEntry] = []


class RecoveryItemOut(BaseModel):
    rec_id: str
    opp_id: str
    amount: Decimal
    status: str
    evidence: dict


class RecoveryPack(BaseModel):
    vendor_id: str
    total: Decimal
    items: list[RecoveryItemOut]


class RecoveryPacksResponse(BaseModel):
    packs: list[RecoveryPack]


class DataQualityCoverage(BaseModel):
    low_confidence_matches: int = 0
    unmatched_count: int = 0
    match_coverage_pct: Decimal = Decimal("0")


class DataQualityEvent(BaseModel):
    id: str
    event_type: str
    detail: dict
    created_at: str


class DataQualityEventsResponse(BaseModel):
    items: list[DataQualityEvent]
