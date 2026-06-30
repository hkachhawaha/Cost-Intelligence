"""ReadModelService — shapes Phase-4 memory + canonical drill-downs into the exact
UI response models (§4.1).

Aggregate reads (dashboard, spend breakdowns, renewals, match coverage) come from
`MemoryService` (pre-computed, sub-50ms). Drill-downs (one contract, its linked
spend, recovery packs, DQ events) read the canonical store directly — already
indexed and carrying lineage. NEVER reads source systems (ingest-once, §5.8).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.contract import Contract
from app.models.matching import MatchResult
from app.models.opportunity import Opportunity, RecoveryItem
from app.models.spend import SpendRecord
from app.services.memory import MemoryService

ZERO = Decimal("0")

# audit_events surfaced in the Data Quality review feed (canonical drill-down).
_DQ_EVENT_TYPES = (
    "match.overridden",
    "match.accepted",
    "match.reassigned",
    "data_quality.flagged",
    "staging.rejected",
)

_SPEND_SECTION = {
    "vendor": "vendor_summary",
    "category": "spend_by_category",
    "cost-center": "spend_by_cost_center",
}

_RENEWAL_WINDOWS = {
    90: ["within_90"],
    180: ["within_90", "within_180"],
    365: ["within_90", "within_180", "within_365"],
}


class ContractNotFoundError(Exception): ...


class ReadModelService:
    def __init__(self, session: AsyncSession, memory: MemoryService):
        self.session = session
        self.memory = memory

    # ── Dashboard (single memory payload) ──────────────────────────────────────
    async def dashboard_kpis(self, tenant_id: str) -> dict:
        return await self.memory.get_kpis(tenant_id)

    # ── Spend Explorer (memory sections) ───────────────────────────────────────
    async def spend_by(self, tenant_id: str, dimension: str) -> dict:
        section = _SPEND_SECTION[dimension]
        items = await self._section_or_empty(tenant_id, section)
        # vendor_summary uses {"vendor_id","spend"}; category/cost-center use {"label","amount"}.
        normalized = [self._to_breakdown_item(row) for row in items]
        return {"dimension": dimension, "items": normalized}

    async def spend_trend(self, tenant_id: str) -> dict:
        return {"items": await self._section_or_empty(tenant_id, "spend_trend")}

    async def match_coverage(self, tenant_id: str) -> dict:
        breakdown = await self._section_or_empty(
            tenant_id, "match_coverage_breakdown", as_dict=True
        )
        dq = await self._section_or_empty(tenant_id, "data_quality_summary", as_dict=True)
        return {
            "po_exact": int(breakdown.get("po_exact", 0)),
            "vendor_amount_date": int(breakdown.get("vendor_amount_date", 0)),
            "ai_inferred": int(breakdown.get("ai_inferred", 0)),
            "unmatched": int(dq.get("unmatched_count", 0)),
            "coverage_pct": str(dq.get("match_coverage_pct", "0")),
        }

    # ── Renewals (memory section, windowed) ────────────────────────────────────
    async def renewals(self, tenant_id: str, window: int) -> dict:
        cal = await self._section_or_empty(tenant_id, "renewal_calendar", as_dict=True)
        keep = _RENEWAL_WINDOWS[window]
        return {k: cal.get(k, []) for k in keep}

    # ── Contracts (list from canonical; detail drill-down) ──────────────────────
    async def contracts_list(self, tenant_id: str, page: int, page_size: int) -> dict:
        from sqlalchemy import func

        total = (
            await self.session.execute(select(func.count()).select_from(Contract))
        ).scalar_one()
        rows = (
            await self.session.scalars(
                select(Contract)
                .order_by(desc(Contract.acv))
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).all()
        return {
            "items": [self._contract_summary(c) for c in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def contract_detail(self, tenant_id: str, contract_id: str) -> dict:
        c = await self.session.get(Contract, UUID(contract_id))
        if c is None:
            raise ContractNotFoundError(contract_id)
        return self._contract_detail(c)

    async def contract_spend(self, tenant_id: str, contract_id: str) -> dict:
        cid = UUID(contract_id)
        spend = (
            await self.session.scalars(
                select(SpendRecord)
                .join(MatchResult, MatchResult.spend_id == SpendRecord.id)
                .where(MatchResult.contract_id == cid)
            )
        ).all()
        total = sum((s.amount for s in spend), ZERO)
        c = await self.session.get(Contract, cid)
        utilization = (total / c.acv * Decimal("100")) if (c and c.acv) else ZERO
        return {
            "contract_id": contract_id,
            "total_matched_spend": str(total),
            "utilization_pct": str(utilization.quantize(Decimal("0.01"))),
            "lines": [
                {
                    "spend_id": str(s.id),
                    "amount": str(s.amount),
                    "spend_date": s.spend_date.isoformat(),
                    "po_number": s.po_number,
                }
                for s in spend
            ],
        }

    # ── Margin Recovery (group recovery_items by contract→vendor into packs) ─────
    async def recovery_packs(self, tenant_id: str) -> dict:
        items = (
            await self.session.scalars(
                select(RecoveryItem).join(Opportunity, Opportunity.id == RecoveryItem.opp_id)
            )
        ).all()
        packs: dict[str, dict] = {}
        for it in items:
            opp = await self.session.get(Opportunity, it.opp_id)
            vid = str(it.vendor_id or (opp.contract_id if opp else "unknown"))
            pack = packs.setdefault(vid, {"vendor_id": vid, "items": [], "total": ZERO})
            pack["items"].append(
                {
                    "rec_id": str(it.id),
                    "opp_id": str(it.opp_id),
                    "amount": str(it.amount),
                    "status": it.status,
                    "evidence": it.evidence,
                }
            )
            pack["total"] += it.amount
        return {"packs": [{**p, "total": str(p["total"])} for p in packs.values()]}

    async def recovery_pack(self, tenant_id: str, rec_id: str) -> dict:
        it = await self.session.get(RecoveryItem, UUID(rec_id))
        if it is None:
            raise ContractNotFoundError(rec_id)
        opp = await self.session.get(Opportunity, it.opp_id)
        vid = str(it.vendor_id or (opp.contract_id if opp else "unknown"))
        return {
            "vendor_id": vid,
            "total": str(it.amount),
            "items": [
                {
                    "rec_id": str(it.id),
                    "opp_id": str(it.opp_id),
                    "amount": str(it.amount),
                    "status": it.status,
                    "evidence": it.evidence,
                }
            ],
        }

    # ── Data Quality ─────────────────────────────────────────────────────────────
    async def dq_coverage(self, tenant_id: str) -> dict:
        return await self._section_or_empty(tenant_id, "data_quality_summary", as_dict=True)

    async def dq_events(self, tenant_id: str, limit: int = 50) -> dict:
        rows = (
            await self.session.scalars(
                select(AuditEvent)
                .where(AuditEvent.event_type.in_(_DQ_EVENT_TYPES))
                .order_by(desc(AuditEvent.created_at))
                .limit(limit)
            )
        ).all()
        return {
            "items": [
                {
                    "id": str(e.event_id),
                    "event_type": e.event_type,
                    "detail": e.payload,
                    "created_at": e.created_at.isoformat(),
                }
                for e in rows
            ]
        }

    # ── helpers ──────────────────────────────────────────────────────────────────
    async def _section_or_empty(self, tenant_id: str, section: str, *, as_dict: bool = False):
        """Return a memory section, or an empty list/dict if memory isn't built yet."""
        from app.services.memory import MemoryNotBuiltError

        try:
            return await self.memory.get_section(tenant_id, section)
        except MemoryNotBuiltError:
            return {} if as_dict else []

    @staticmethod
    def _to_breakdown_item(row: dict) -> dict:
        if "label" in row and "amount" in row:
            return {"label": row["label"], "amount": row["amount"]}
        # vendor_summary shape → {label: vendor_id, amount: spend}
        return {"label": row.get("vendor_id", "unknown"), "amount": row.get("spend", "0")}

    @staticmethod
    def _contract_summary(c: Contract) -> dict:
        return {
            "id": str(c.id),
            "vendor_id": str(c.vendor_id),
            "acv": str(c.acv) if c.acv is not None else None,
            "tcv": str(c.tcv) if c.tcv is not None else None,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "renewal_type": c.renewal_type,
            "status": c.status,
            "indexation": {
                "index_type": c.index_type,
                "indexed_share": str(c.indexed_share or 0),
                "has_indexation": bool(c.index_type),
            },
        }

    @classmethod
    def _contract_detail(cls, c: Contract) -> dict:
        return {
            **cls._contract_summary(c),
            "effective_date": c.effective_date.isoformat() if c.effective_date else None,
            "renewal_notice_days": c.renewal_notice_days,
            "uplift_pct": str(c.uplift_pct or 0),
            "yearly_commit": str(c.yearly_commit or 0),
            "payment_term_days": c.payment_term_days,
            "currency": c.currency,
            "po_numbers": c.po_numbers or [],
            "source_system": c.source_system,
        }
