"""KpiComputer — every KPI computed deterministically from the canonical store.

No LLM, no float. Invoked once per sync by MemoryService.build(). Reads the
contracts/spend/matches/opportunities that Phases 1–3 produced; every dollar
figure is provable against source records (§5.6).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.matching import MatchResult
from app.models.opportunity import Opportunity
from app.models.spend import SpendRecord

ZERO = Decimal("0")


@dataclass
class ComputedMemory:
    scalars: dict
    summaries: dict

    def cache_payload(self) -> dict:
        return {
            **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.scalars.items()},
            **self.summaries,
        }


class KpiComputer:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def compute_all(self, tenant_id: str) -> ComputedMemory:
        spend = (await self.session.scalars(select(SpendRecord))).all()
        contracts = (await self.session.scalars(select(Contract))).all()
        matches = (await self.session.scalars(select(MatchResult))).all()
        opps = (await self.session.scalars(select(Opportunity))).all()

        match_by_spend = {m.spend_id: m for m in matches}
        contract_by_id = {c.id: c for c in contracts}
        scalars: dict = {}
        summaries: dict = {}

        total_spend = sum((s.amount for s in spend), ZERO)
        scalars["total_spend"] = total_spend
        scalars["spend_record_count"] = len(spend)
        scalars["contract_count"] = len(contracts)

        matched_amount = sum(
            (
                s.amount
                for s in spend
                if (m := match_by_spend.get(s.id)) and m.contract_id is not None
            ),
            ZERO,
        )
        scalars["match_coverage_pct"] = self._pct(matched_amount, total_spend)

        active_ids = {c.id for c in contracts if c.status == "active"}
        sum_amount = sum(
            (
                s.amount
                for s in spend
                if (m := match_by_spend.get(s.id)) and m.contract_id in active_ids
            ),
            ZERO,
        )
        scalars["spend_under_management_pct"] = self._pct(sum_amount, total_spend)

        with_po = sum(1 for s in spend if s.po_number)
        scalars["po_coverage_pct"] = self._pct(Decimal(with_po), Decimal(len(spend) or 1))

        compliant = ZERO
        for s in spend:
            m = match_by_spend.get(s.id)
            if m and m.contract_id is not None and (c := contract_by_id.get(m.contract_id)):
                if c.start_date and c.end_date and c.start_date <= s.spend_date <= c.end_date:
                    compliant += s.amount
        scalars["contract_compliance_pct"] = self._pct(compliant, matched_amount or total_spend)

        savings = sum((o.impact for o in opps if o.bucket == "savings"), ZERO)
        recovery = sum((o.impact for o in opps if o.bucket == "recovery"), ZERO)
        realized = sum((o.impact for o in opps if o.status == "realized"), ZERO)
        scalars["total_savings"] = savings
        scalars["total_recovery"] = recovery
        scalars["total_identified"] = savings + recovery
        scalars["total_realized"] = realized
        scalars["opportunity_count"] = len(opps)

        count_by_type: dict[str, int] = defaultdict(int)
        amount_by_type: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for o in opps:
            count_by_type[o.type] += 1
            amount_by_type[o.type] += o.impact
        summaries["opportunity_count_by_type"] = dict(count_by_type)
        summaries["opportunity_amount_by_type"] = {k: str(v) for k, v in amount_by_type.items()}

        ranked = sorted(opps, key=lambda o: o.impact * o.confidence, reverse=True)[:10]
        summaries["top_opportunities"] = [
            {
                "id": str(o.id),
                "type": o.type,
                "bucket": o.bucket,
                "impact": str(o.impact),
                "confidence": str(o.confidence),
                "contract_id": str(o.contract_id) if o.contract_id else None,
                "status": o.status,
            }
            for o in ranked
        ]

        scalars["vendor_count"] = len({s.vendor_id for s in spend})
        summaries["vendor_summary"] = self._vendor_summary(spend)
        summaries["renewal_calendar"] = self._renewal_calendar(contracts)
        summaries["spend_by_category"] = self._group_sum(
            spend, key=lambda s: s.gl_code or "Uncategorized"
        )
        summaries["spend_by_cost_center"] = self._group_sum(
            spend, key=lambda s: s.cost_center or "None"
        )
        summaries["spend_trend"] = self._monthly_trend(spend)

        method_counts: dict[str, int] = defaultdict(int)
        for m in matches:
            method_counts[m.method] += 1
        summaries["match_coverage_breakdown"] = dict(method_counts)

        low_conf = sum(
            1 for m in matches if m.contract_id and Decimal("0.5") <= m.confidence < Decimal("0.7")
        )
        unmatched = sum(1 for m in matches if m.contract_id is None)
        summaries["data_quality_summary"] = {
            "low_confidence_matches": low_conf,
            "unmatched_count": unmatched,
            "match_coverage_pct": str(scalars["match_coverage_pct"]),
        }
        summaries["alerts"] = self._alerts(contracts, opps)

        return ComputedMemory(scalars=scalars, summaries=summaries)

    # ── helpers ──
    @staticmethod
    def _pct(num: Decimal, den: Decimal) -> Decimal:
        if not den:
            return ZERO
        return (num / den * Decimal("100")).quantize(Decimal("0.01"))

    @staticmethod
    def _group_sum(spend, key) -> list[dict]:
        agg: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for s in spend:
            agg[key(s)] += s.amount
        return sorted(
            ({"label": k, "amount": str(v)} for k, v in agg.items()),
            key=lambda d: Decimal(d["amount"]),
            reverse=True,
        )

    @staticmethod
    def _monthly_trend(spend) -> list[dict]:
        agg: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for s in spend:
            agg[s.spend_date.strftime("%Y-%m")] += s.amount
        return [{"month": m, "amount": str(agg[m])} for m in sorted(agg)]

    @staticmethod
    def _vendor_summary(spend) -> list[dict]:
        spend_by_vendor: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for s in spend:
            spend_by_vendor[str(s.vendor_id)] += s.amount
        return sorted(
            (
                {"vendor_id": v, "spend": str(amt), "opportunity": "0"}
                for v, amt in spend_by_vendor.items()
            ),
            key=lambda d: Decimal(d["spend"]),
            reverse=True,
        )[:50]

    @staticmethod
    def _renewal_calendar(contracts) -> dict:
        today = date.today()
        buckets: dict[str, list] = {"within_90": [], "within_180": [], "within_365": []}
        for c in contracts:
            if c.end_date is None:
                continue
            days = (c.end_date - today).days
            if days < 0:
                continue  # already expired — a renewal calendar is forward-looking only
            notice = c.renewal_notice_days or 0
            entry = {
                "contract_id": str(c.id),
                "vendor_id": str(c.vendor_id),
                "end_date": c.end_date.isoformat(),
                "days_to_end": days,
                "renewal_type": c.renewal_type,
                "notice_deadline": (c.end_date - timedelta(days=notice)).isoformat(),
                "acv": str(c.acv) if c.acv is not None else None,
            }
            if 0 <= days <= 90:
                buckets["within_90"].append(entry)
            elif days <= 180:
                buckets["within_180"].append(entry)
            elif days <= 365:
                buckets["within_365"].append(entry)
        return buckets

    @staticmethod
    def _alerts(contracts, opps) -> list[dict]:
        alerts: list[dict] = []
        today = date.today()
        for c in contracts:
            if c.renewal_type == "auto" and c.end_date is not None:
                deadline = c.end_date - timedelta(days=c.renewal_notice_days or 0)
                if today >= deadline:
                    alerts.append(
                        {
                            "kind": "auto_renewal_window",
                            "contract_id": str(c.id),
                            "notice_deadline": deadline.isoformat(),
                            "severity": "high",
                        }
                    )
        for o in opps:
            if o.type in ("post_expiry", "duplicate_invoice") and o.status == "detected":
                alerts.append(
                    {
                        "kind": o.type,
                        "opportunity_id": str(o.id),
                        "impact": str(o.impact),
                        "severity": "medium",
                    }
                )
        return alerts
