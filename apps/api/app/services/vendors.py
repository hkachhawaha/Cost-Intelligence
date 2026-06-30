"""VendorService (§5.1) — canonical vendor rollup + consolidation-candidate detection.

A consolidation candidate is a CATEGORY with fragmented spend across many vendors.
All figures computed in Python (§5.6); `fragmentation_score = 1 - largest_vendor_share`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.config import settings


@dataclass
class VendorRollup:
    vendor_id: str
    name: str
    total_spend: Decimal
    total_acv: Decimal
    contract_count: int
    matched_spend_pct: Decimal


@dataclass
class ConsolidationCandidate:
    scope: str  # 'category' | 'vendor'
    key: str
    label: str
    vendor_count: int
    contract_count: int
    total_spend: Decimal
    fragmentation_score: Decimal  # 0..1 — higher = more fragmented = better candidate
    rationale: dict


class VendorService:
    @property
    def min_vendors(self) -> int:
        return settings.consolidation_min_vendors

    @property
    def min_category_spend(self) -> Decimal:
        return Decimal(str(settings.consolidation_min_category_spend))

    async def rollup(self, session: AsyncSession, principal: Principal) -> list[VendorRollup]:
        rows = await session.execute(
            text(
                """
                SELECT v.id, v.name,
                       COALESCE(SUM(s.amount), 0)        AS total_spend,
                       COALESCE(SUM(DISTINCT c.acv), 0)  AS total_acv,
                       COUNT(DISTINCT c.id)              AS contract_count,
                       COALESCE(SUM(s.amount) FILTER (WHERE s.contract_id IS NOT NULL), 0)
                                                         AS matched_spend
                FROM vendors v
                LEFT JOIN contracts c     ON c.vendor_id = v.id
                LEFT JOIN spend_records s ON s.vendor_id = v.id
                GROUP BY v.id, v.name
                ORDER BY total_spend DESC
                """
            )
        )
        out: list[VendorRollup] = []
        for r in rows.mappings().all():
            total = Decimal(r["total_spend"])
            matched = Decimal(r["matched_spend"])
            pct = (matched / total) if total else Decimal("0")
            out.append(
                VendorRollup(
                    vendor_id=str(r["id"]),
                    name=r["name"],
                    total_spend=total,
                    total_acv=Decimal(r["total_acv"]),
                    contract_count=r["contract_count"],
                    matched_spend_pct=pct,
                )
            )
        return out

    async def consolidation_candidates(
        self, session: AsyncSession, principal: Principal
    ) -> list[ConsolidationCandidate]:
        rows = await session.execute(
            text(
                """
                SELECT s.taxonomy_l1 AS category, s.vendor_id, v.name AS vendor_name,
                       SUM(COALESCE(s.base_amount, s.amount)) AS vendor_spend
                FROM spend_records s
                JOIN vendors v ON v.id = s.vendor_id
                WHERE s.taxonomy_l1 IS NOT NULL
                GROUP BY s.taxonomy_l1, s.vendor_id, v.name
                """
            )
        )
        by_category: dict[str, list[tuple[str, str, Decimal]]] = {}
        for r in rows.mappings().all():
            by_category.setdefault(r["category"], []).append(
                (str(r["vendor_id"]), r["vendor_name"], Decimal(r["vendor_spend"] or 0))
            )

        candidates: list[ConsolidationCandidate] = []
        for category, vendors in by_category.items():
            total = sum((v[2] for v in vendors), Decimal("0"))
            vendor_count = len(vendors)
            if vendor_count < self.min_vendors or total < self.min_category_spend:
                continue
            largest = max(vendors, key=lambda v: v[2])
            largest_share = (largest[2] / total) if total else Decimal("0")
            fragmentation = Decimal("1") - largest_share
            top = sorted(vendors, key=lambda v: v[2], reverse=True)[:5]
            candidates.append(
                ConsolidationCandidate(
                    scope="category",
                    key=category,
                    label=f"{category} — {vendor_count} vendors, ${total:,.0f}",
                    vendor_count=vendor_count,
                    contract_count=vendor_count,
                    total_spend=total,
                    fragmentation_score=fragmentation,
                    rationale={
                        "total_spend": str(total),
                        "vendor_count": vendor_count,
                        "largest_vendor": largest[1],
                        "largest_share": str(largest_share),
                        "top_vendors": [{"name": v[1], "spend": str(v[2])} for v in top],
                    },
                )
            )
        candidates.sort(key=lambda c: c.fragmentation_score * c.total_spend, reverse=True)
        return candidates


vendor_service = VendorService()
