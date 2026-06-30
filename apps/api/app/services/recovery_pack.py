"""RecoveryPackBuilder (§5.5) — per-vendor recovery packs with per-line-item evidence.

For line-item findings (above_rate, volume_tier) one RecoveryItem is materialized per
overcharged/under-tiered line so a supplier challenge letter can cite each SKU. Header
recoverables (e.g. duplicate_invoice) become a single item. Only `counts_in_total`
opportunities contribute (the coexistence guard has already deduped).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity, RecoveryItem, RecoveryPack


class RecoveryPackBuilder:
    LINE_TYPES = {"above_rate", "volume_tier"}

    async def build_for_vendor(
        self,
        tenant_id: str,
        vendor_id: str | None,
        opps: list[Opportunity],
        session: AsyncSession,
    ) -> RecoveryPack:
        pack = RecoveryPack(
            tenant_id=UUID(tenant_id),
            vendor_id=UUID(vendor_id) if vendor_id else None,
            status="draft",
            total_amount=Decimal("0"),
        )
        session.add(pack)
        await session.flush()  # get pack.id

        total = Decimal("0")
        for opp in opps:
            if opp.bucket != "recovery" or not opp.counts_in_total:
                continue
            if opp.type in self.LINE_TYPES:
                lines = opp.evidence.get("line_overcharges") or opp.evidence.get("lines") or []
                for ln in lines:
                    delta = Decimal(str(ln.get("delta") or ln.get("line_saving") or "0"))
                    session.add(
                        RecoveryItem(
                            tenant_id=UUID(tenant_id),
                            pack_id=pack.id,
                            opp_id=opp.id,
                            vendor_id=pack.vendor_id,
                            amount=delta,
                            status="detected",
                            line_item_id=UUID(ln["line_item_id"])
                            if ln.get("line_item_id")
                            else None,
                            sku=ln.get("sku"),
                            quantity=Decimal(str(ln["quantity"])) if ln.get("quantity") else None,
                            billed_rate=Decimal(str(ln.get("billed_rate", "0"))),
                            contracted_rate=Decimal(
                                str(ln.get("contracted_rate") or ln.get("qualified_rate", "0"))
                            ),
                            line_delta=delta,
                            evidence={"opp_type": opp.type, **ln},
                        )
                    )
                    total += delta
            else:
                session.add(
                    RecoveryItem(
                        tenant_id=UUID(tenant_id),
                        pack_id=pack.id,
                        opp_id=opp.id,
                        vendor_id=pack.vendor_id,
                        amount=opp.impact,
                        status="detected",
                        evidence=opp.evidence,
                    )
                )
                total += opp.impact

        pack.total_amount = total
        await session.flush()
        return pack


recovery_pack_builder = RecoveryPackBuilder()
