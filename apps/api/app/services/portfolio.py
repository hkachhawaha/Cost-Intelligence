"""PortfolioService (§5.3) — multi-entity rollup, RBAC-gated to portfolio_admin/admin.

By-entity spend, spend-under-management, and opportunity totals — all from the canonical
store / memory. Raises NotAuthorized for other roles (also re-checked at the route).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal


class NotAuthorized(Exception): ...


@dataclass
class EntityRollup:
    entity_id: str
    entity_name: str
    total_spend: Decimal
    spend_under_management_pct: Decimal
    identified_savings: Decimal
    identified_recovery: Decimal


class PortfolioService:
    ALLOWED_ROLES = {"portfolio_admin", "admin"}

    async def by_entity(self, session: AsyncSession, principal: Principal) -> list[EntityRollup]:
        if principal.role not in self.ALLOWED_ROLES:
            raise NotAuthorized("portfolio view requires portfolio_admin")
        rows = await session.execute(
            text(
                """
                SELECT e.id AS entity_id, e.name AS entity_name,
                       COALESCE(SUM(s.amount), 0) AS total_spend,
                       COALESCE(SUM(s.amount) FILTER (WHERE s.contract_id IS NOT NULL), 0)
                            AS matched_spend,
                       COALESCE(SUM(o.impact) FILTER (WHERE o.bucket = 'savings'), 0)  AS savings,
                       COALESCE(SUM(o.impact) FILTER (WHERE o.bucket = 'recovery'), 0) AS recovery
                FROM entities e
                LEFT JOIN contracts c     ON c.entity_id = e.id
                LEFT JOIN spend_records s ON s.contract_id = c.id
                LEFT JOIN opportunities o ON o.contract_id = c.id
                GROUP BY e.id, e.name
                ORDER BY total_spend DESC
                """
            )
        )
        out: list[EntityRollup] = []
        for r in rows.mappings().all():
            total = Decimal(r["total_spend"])
            matched = Decimal(r["matched_spend"])
            sum_pct = (matched / total) if total else Decimal("0")
            out.append(
                EntityRollup(
                    entity_id=str(r["entity_id"]),
                    entity_name=r["entity_name"],
                    total_spend=total,
                    spend_under_management_pct=sum_pct,
                    identified_savings=Decimal(r["savings"]),
                    identified_recovery=Decimal(r["recovery"]),
                )
            )
        return out


portfolio_service = PortfolioService()


class PortfolioGovernanceService:
    """Phase 10 multi-entity governance (§8). All first-party: consolidation, same-vendor
    multi-entity leverage, per-entity P&L impact. RBAC-gated to portfolio_admin/admin."""

    ALLOWED_ROLES = {"portfolio_admin", "admin"}

    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def _authorize(self, principal: Principal) -> None:
        if principal.role not in self.ALLOWED_ROLES:
            raise NotAuthorized("portfolio governance requires portfolio_admin")

    async def consolidate_spend(self, principal: Principal, period: date) -> dict:
        """Cross-entity consolidation for a period: total + per-entity spend/SUM%/opportunity."""
        self._authorize(principal)
        rows = await self.session.execute(
            text(
                """
                SELECT e.id AS entity_id, e.name AS entity_name,
                       COALESCE(SUM(s.amount), 0) AS spend,
                       COALESCE(SUM(s.amount) FILTER (WHERE s.contract_id IS NOT NULL), 0)
                            AS matched,
                       COALESCE(SUM(o.impact) FILTER (WHERE o.bucket = 'savings'), 0)  AS savings,
                       COALESCE(SUM(o.impact) FILTER (WHERE o.bucket = 'recovery'), 0) AS recovery
                FROM entities e
                LEFT JOIN spend_records s
                       ON s.entity_id = e.id
                      AND date_trunc('month', s.spend_date) = date_trunc('month', :period)
                LEFT JOIN opportunities o ON o.contract_id = s.contract_id
                GROUP BY e.id, e.name
                ORDER BY spend DESC
                """
            ),
            {"period": period},
        )
        by_entity: list[dict] = []
        total_spend = total_savings = total_recovery = total_matched = Decimal("0")
        for r in rows.mappings().all():
            spend, matched = Decimal(r["spend"]), Decimal(r["matched"])
            savings, recovery = Decimal(r["savings"]), Decimal(r["recovery"])
            by_entity.append({
                "entity_id": str(r["entity_id"]), "name": r["entity_name"],
                "spend": str(spend),
                "sum_pct": str((matched / spend) if spend else Decimal("0")),
                "savings": str(savings), "recovery": str(recovery),
            })
            total_spend += spend
            total_matched += matched
            total_savings += savings
            total_recovery += recovery
        sum_pct = (total_matched / total_spend) if total_spend else Decimal("0")
        return {"period": period.isoformat(), "total_spend": str(total_spend),
                "spend_under_mgmt_pct": str(sum_pct), "total_savings": str(total_savings),
                "total_recovery": str(total_recovery), "by_entity": by_entity}

    async def detect_vendor_leverage(self, principal: Principal) -> list[dict]:
        """Same canonical vendor spanning ≥2 entities → consolidation leverage. Pure
        first-party signal: counts entities + aggregates spend; never claims a market price."""
        self._authorize(principal)
        rows = await self.session.execute(
            text(
                """
                SELECT s.vendor_id AS vendor_id,
                       COALESCE(v.name, MIN(s.vendor_name_raw)) AS vendor_name,
                       s.entity_id  AS entity_id,
                       COALESCE(SUM(s.amount), 0) AS spend
                FROM spend_records s
                LEFT JOIN vendors v ON v.id = s.vendor_id
                WHERE s.entity_id IS NOT NULL
                GROUP BY s.vendor_id, v.name, s.entity_id
                """
            )
        )
        agg: dict[str, dict] = {}
        for r in rows.mappings().all():
            vid = str(r["vendor_id"])
            entry = agg.setdefault(
                vid, {"vendor_name": r["vendor_name"], "entities": set(), "spend": Decimal("0")}
            )
            entry["entities"].add(str(r["entity_id"]))
            entry["spend"] += Decimal(r["spend"])
        leverage = [
            {
                "vendor_id": vid,
                "vendor": v["vendor_name"],
                "entities": sorted(v["entities"]),
                "entity_count": len(v["entities"]),
                "total_spend": str(v["spend"]),
                "leverage_estimate": (
                    f"consolidation candidate: {len(v['entities'])} entities, fragmented"
                ),
                "note": "first-party leverage signal; no external pricing used",
            }
            for vid, v in agg.items()
            if len(v["entities"]) >= 2  # multi-entity → leverage candidate
        ]
        return sorted(leverage, key=lambda x: Decimal(x["total_spend"]), reverse=True)

    async def per_entity_pnl_impact(self, principal: Principal, period: date) -> list[dict]:
        """Attribute identified savings/recovery to each entity's P&L (first-party)."""
        consolidated = await self.consolidate_spend(principal, period)
        out = []
        for e in consolidated["by_entity"]:
            savings, recovery = Decimal(e["savings"]), Decimal(e["recovery"])
            out.append({"entity_id": e["entity_id"], "name": e["name"],
                        "identified_savings": str(savings),
                        "identified_recovery": str(recovery),
                        "pnl_impact": str(savings + recovery)})
        return out
