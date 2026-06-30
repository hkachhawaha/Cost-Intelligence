"""IndexationService (§5.2) — index/COLA register + exposure modeling.

    indexed_exposure = ACV × indexed_share × assumed_move          (§8.6)

`assumed_move` is a FIRST-PARTY ASSUMPTION supplied by the user (the slider), NOT an
external CPI feed. The result is advisory forward cost-risk visibility. All Decimal math.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal


@dataclass
class ExposureLine:
    contract_id: str
    vendor_name: str
    acv: Decimal
    index_type: str
    indexed_share: Decimal
    indexed_exposure: Decimal
    formula: str


@dataclass
class ExposureResult:
    assumed_move_pct: Decimal
    total_indexed_exposure: Decimal
    lines: list[ExposureLine]


class IndexationService:
    async def register(self, session: AsyncSession, principal: Principal) -> list[dict]:
        rows = await session.execute(
            text(
                """
                SELECT ir.contract_id, v.name AS vendor_name, c.acv,
                       ir.index_type, ir.indexed_share
                FROM index_register ir
                JOIN contracts c ON c.id = ir.contract_id
                JOIN vendors  v ON v.id = c.vendor_id
                ORDER BY c.acv * ir.indexed_share DESC
                """
            )
        )
        return [dict(r) for r in rows.mappings().all()]

    async def exposure(
        self, session: AsyncSession, principal: Principal, *, move_pct: Decimal
    ) -> ExposureResult:
        """move_pct is the user's assumed adverse index move (e.g. 10 → 10%)."""
        assumed_move = move_pct / Decimal("100")
        register = await self.register(session, principal)
        lines: list[ExposureLine] = []
        total = Decimal("0")
        for r in register:
            acv = Decimal(str(r["acv"] or 0))
            share = Decimal(str(r["indexed_share"] or 0))
            exposure = (acv * share * assumed_move).quantize(Decimal("0.01"))  # FIRST-PARTY
            total += exposure
            lines.append(
                ExposureLine(
                    contract_id=str(r["contract_id"]),
                    vendor_name=r["vendor_name"],
                    acv=acv,
                    index_type=r["index_type"],
                    indexed_share=share,
                    indexed_exposure=exposure,
                    formula="ACV × indexed_share × assumed_move",
                )
            )
        return ExposureResult(assumed_move_pct=move_pct, total_indexed_exposure=total, lines=lines)


indexation_service = IndexationService()
