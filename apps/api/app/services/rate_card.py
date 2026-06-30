"""RateCardService (§5.3) — lookup of verified rate cards for the line-item rules.

Only VERIFIED cards (`verified_at IS NOT NULL`) drive $ math — the HITL gate. Tiers are
eager-loaded; RLS scopes to the current tenant automatically.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.rate_card import ContractRateCard


class RateCardService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def for_contract(self, contract_id: str | UUID) -> dict[str, ContractRateCard]:
        """{canonical_sku: ContractRateCard} for a contract (verified only, tiers loaded)."""
        cid = contract_id if isinstance(contract_id, UUID) else UUID(str(contract_id))
        rows = (
            (
                await self.session.execute(
                    select(ContractRateCard)
                    .where(ContractRateCard.contract_id == cid)
                    .where(ContractRateCard.verified_at.isnot(None))
                    .options(selectinload(ContractRateCard.tiers))
                )
            )
            .scalars()
            .all()
        )
        return {rc.sku: rc for rc in rows}

    @staticmethod
    def split_tiered(
        cards: dict[str, ContractRateCard],
    ) -> tuple[dict[str, ContractRateCard], dict[str, ContractRateCard]]:
        flat = {k: v for k, v in cards.items() if not v.is_tiered}
        tiered = {k: v for k, v in cards.items() if v.is_tiered}
        return flat, tiered
