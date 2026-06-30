"""Cold/warm tiering (§10.2). Three tiers:

  HOT  : recent N months in Postgres (partitioned) — OLTP + detection write path.
  WARM : full history mirrored to ClickHouse (columnar) — sub-second aggregation for Spend
         Explorer / Portfolio / trend charts over 10M+ rows.
  COLD : history beyond the warm window archived to S3/Parquet — queried on demand only.

The dashboard READ PATH never touches hot/warm directly — it reads the P4 memory layer
(precomputed KPIs). Warm/cold are for drilldowns and analytical queries. The actual movement
is infra-bound (ClickHouse + S3) and wired in deployment; here it is recorded as tiering
bookkeeping in `spend_tier_metadata` so the platform tracks where each period lives.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.commitment import SpendTierMetadata

logger = logging.getLogger("tiering")


class TierManager:
    def __init__(self, session: AsyncSession | None = None, tenant_id: str | None = None):
        self.session = session
        self.tenant_id = tenant_id

    def tier_for(self, period: date, today: date) -> str:
        """Deterministic tier policy (pure): hot within retain window, warm within warm
        window, cold beyond. Used to plan demotions."""
        months_old = (today.year * 12 + today.month) - (period.year * 12 + period.month)
        if months_old < settings.spend_hot_retain_months:
            return "hot"
        if months_old < settings.spend_warm_retain_months:
            return "warm"
        return "cold"

    async def record_tier(self, period: date, tier: str, row_count: int = 0) -> SpendTierMetadata:
        """Upsert the tiering bookkeeping row for a period (idempotent on (tenant, period))."""
        assert self.session is not None and self.tenant_id is not None
        existing = await self.session.scalar(
            select(SpendTierMetadata)
            .where(SpendTierMetadata.tenant_id == UUID(self.tenant_id))
            .where(SpendTierMetadata.period == period)
        )
        if existing:
            existing.tier = tier
            existing.row_count = row_count or existing.row_count
            if tier == "cold":
                existing.archived_at = datetime.now(UTC)
            await self.session.flush()
            return existing
        row = SpendTierMetadata(
            id=uuid4(), tenant_id=UUID(self.tenant_id), period=period, tier=tier,
            row_count=row_count,
            archived_at=datetime.now(UTC) if tier == "cold" else None,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def mirror_to_clickhouse(self, period: date) -> None:
        """Insert the period's spend into the ClickHouse columnar table (MergeTree,
        ORDER BY (tenant_id, spend_date, vendor_id)). Infra-bound; no-op when ClickHouse is
        not configured (the warm tier degrades to Postgres reads — §15.1)."""
        logger.info("tiering.mirror_to_clickhouse period=%s (infra-bound; tracked only)", period)

    async def demote(self, period: date, today: date) -> str:
        """Detached Postgres partition → warm (ClickHouse) → if beyond warm window, cold
        (S3/Parquet). Records the resulting tier in bookkeeping; movement is infra-bound."""
        tier = self.tier_for(period, today)
        if self.session is not None and self.tenant_id is not None:
            await self.record_tier(period, tier)
        if tier in ("warm", "cold"):
            await self.mirror_to_clickhouse(period)
        return tier
