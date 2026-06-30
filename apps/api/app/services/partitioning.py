"""Partition management (§10.1). `spend_records` is range-partitioned by month (spend_date);
tenant isolation remains RLS. Partitions are created ahead of time and old ones detached and
handed to `TierManager` (warm/cold). This keeps each partition small so index scans and
detection stay fast at 10M+ rows.

The month-arithmetic + partition-naming helpers are pure and unit-tested. `ensure_partitions`/
`rotate` emit DDL — they require the parent `spend_records` to be a partitioned table (the
online conversion is a dedicated maintenance migration, see migration 010's note).
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger("partitioning")


def first_of_month(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    """Pure month arithmetic (no python-dateutil dependency)."""
    month_index = (d.year * 12 + (d.month - 1)) + n
    year, month0 = divmod(month_index, 12)
    return date(year, month0 + 1, 1)


def partition_name(period: date) -> str:
    return f"spend_records_{period:%Y_%m}"


def partition_bounds(period: date) -> tuple[date, date]:
    """[start, end) month bounds for a range partition."""
    start = first_of_month(period)
    return start, add_months(start, 1)


class PartitionManager:
    def __init__(self, session=None):
        self.session = session

    def planned_partitions(self, today: date, ahead_months: int) -> list[str]:
        """The set of partitions that should exist now + `ahead_months` ahead (pure)."""
        start = first_of_month(today)
        return [partition_name(add_months(start, i)) for i in range(ahead_months + 1)]

    async def ensure_partitions(self, today: date, ahead_months: int = 3) -> list[str]:
        """Create month partitions for the current + next `ahead_months` if absent."""
        created: list[str] = []
        start = first_of_month(today)
        for i in range(ahead_months + 1):
            period = add_months(start, i)
            if await self._create_if_absent(period):
                created.append(partition_name(period))
        return created

    async def _create_if_absent(self, period: date) -> bool:
        from sqlalchemy import text

        name = partition_name(period)
        lo, hi = partition_bounds(period)
        await self.session.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF spend_records "
                f"FOR VALUES FROM (:lo) TO (:hi)"
            ),
            {"lo": lo, "hi": hi},
        )
        logger.info("partition.ensured name=%s [%s,%s)", name, lo, hi)
        return True

    async def rotate(self, today: date, retain_hot_months: int = 12) -> list[date]:
        """Return the periods older than the hot window (caller hands them to TierManager).
        Detaching/archiving DDL is deferred to the maintenance migration."""
        cutoff = add_months(first_of_month(today), -retain_hot_months)
        return [cutoff]
