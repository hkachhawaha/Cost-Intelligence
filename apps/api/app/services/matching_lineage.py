"""Confidence propagation seam (consumed by Phase 3 detection, §8.2 step 4).

A detected opportunity inherits the confidence of the match(es) it rests on; a
multi-spend opportunity is only as trustworthy as its weakest link (MIN).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.matching import MatchResult


async def confidence_for_spend(session: AsyncSession, spend_id: UUID) -> Decimal:
    mr = (
        await session.execute(select(MatchResult).where(MatchResult.spend_id == spend_id))
    ).scalar_one_or_none()
    return mr.confidence if mr else Decimal("0.000")


async def aggregate_confidence(session: AsyncSession, spend_ids: list[UUID]) -> Decimal:
    """MIN of the underlying match confidences — weakest link governs."""
    if not spend_ids:
        return Decimal("0.000")
    rows = (
        (
            await session.execute(
                select(MatchResult.confidence).where(MatchResult.spend_id.in_(spend_ids))
            )
        )
        .scalars()
        .all()
    )
    return min(rows) if rows else Decimal("0.000")
