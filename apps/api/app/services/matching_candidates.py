"""Candidate retrieval — narrows the contract search space before scoring.

A candidate is any contract for the spend's vendor whose term overlaps a padded
window around the spend date, keeping matching O(spend × small_k). RLS scopes to
the tenant automatically.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.spend import SpendRecord

CANDIDATE_WINDOW_DAYS = 90


class CandidateRetrievalService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def for_spend(self, spend: SpendRecord) -> list[Contract]:
        lo = spend.spend_date - timedelta(days=CANDIDATE_WINDOW_DAYS)
        hi = spend.spend_date + timedelta(days=CANDIDATE_WINDOW_DAYS)
        stmt = (
            select(Contract)
            .where(Contract.vendor_id == spend.vendor_id)
            .where(Contract.end_date >= lo)
            .where(Contract.start_date <= hi)
            .order_by(Contract.start_date.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())
