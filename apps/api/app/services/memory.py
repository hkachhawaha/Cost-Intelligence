"""MemoryService — build / read / stale / refresh / invalidate the tenant memory
snapshot (Store 1) and its Redis cache (Store 3).

Contract:
  - build()      : runs after a full sync. Computes every KPI in Python, writes the
                   Postgres snapshot (source of truth), then warms Redis.
  - get_kpis()   : Redis-first with Postgres fallback (operational hot path); a Redis
                   outage degrades gracefully to Postgres.
  - mark_stale() : source changed but no Refresh yet — sets the UI stale banner
                   WITHOUT discarding intelligence (§5.8).
  - invalidate() : drop the Redis copy (Postgres survives; next read re-warms).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kpi_cache import RedisKpiCache
from app.models.memory import TenantMemory
from app.services.memory_kpis import KpiComputer

logger = logging.getLogger("memory")

_SECTIONS = (
    "renewal_calendar",
    "spend_by_category",
    "spend_by_cost_center",
    "spend_trend",
    "vendor_summary",
    "top_opportunities",
    "match_coverage_breakdown",
    "data_quality_summary",
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class MemoryNotBuiltError(Exception): ...


class UnknownMemorySectionError(Exception): ...


class MemoryService:
    def __init__(self, session: AsyncSession, cache: RedisKpiCache, kpis: KpiComputer):
        self.session = session
        self.cache = cache
        self.kpis = kpis

    # ── BUILD ──
    async def build(
        self,
        tenant_id: str,
        *,
        source_fingerprint: str | None = None,
        build_run_id: str | None = None,
    ) -> TenantMemory:
        logger.info("memory.build start tenant=%s", tenant_id)
        computed = await self.kpis.compute_all(tenant_id)  # ALL $ math in code (§5.6)

        prior = await self.session.get(TenantMemory, tenant_id)
        next_version = (prior.memory_version + 1) if prior else 1

        from uuid import UUID

        payload = {
            "tenant_id": UUID(tenant_id),
            "last_synced_at": utcnow(),
            "stale": False,
            "memory_version": next_version,
            "build_run_id": UUID(build_run_id) if build_run_id else None,
            "source_fingerprint": source_fingerprint,
            **computed.scalars,
            **computed.summaries,
            "kpi_snapshot": computed.cache_payload(),
        }
        stmt = (
            pg_insert(TenantMemory)
            .values(**payload)
            .on_conflict_do_update(
                index_elements=["tenant_id"],
                set_={k: v for k, v in payload.items() if k != "tenant_id"}
                | {"updated_at": utcnow()},
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()
        # populate_existing: the Core upsert bypasses the ORM, so a `prior` row left
        # in the identity map (expire_on_commit=False) would be stale on a rebuild.
        snapshot = await self.session.get(TenantMemory, UUID(tenant_id), populate_existing=True)
        assert snapshot is not None  # just upserted above

        # Warm Redis AFTER the Postgres commit — cache can never lead the source of truth.
        await self._warm_redis(tenant_id, computed.cache_payload(), version=next_version)
        logger.info("memory.build done tenant=%s version=%s", tenant_id, next_version)
        return snapshot

    # ── READ (operational hot path) ──
    async def get_kpis(self, tenant_id: str) -> dict:
        try:
            cached = await self.cache.get_snapshot(tenant_id)
            if cached is not None:
                return cached
        except Exception:  # noqa: BLE001 — Redis down ⇒ fall back to Postgres (§9.5)
            logger.warning("memory.get_kpis redis_unavailable tenant=%s", tenant_id)
            cached = None

        row = await self.session.get(TenantMemory, tenant_id)
        if row is None:
            return {"initialized": False, "stale": False, "last_synced_at": None}

        payload = dict(row.kpi_snapshot) | {
            "initialized": True,
            "stale": row.stale,
            "last_synced_at": row.last_synced_at.isoformat(),
            "memory_version": row.memory_version,
        }
        try:
            await self.cache.set_snapshot(tenant_id, payload, version=row.memory_version)
        except Exception:  # noqa: BLE001
            pass
        return payload

    async def get_section(self, tenant_id: str, section: str) -> dict | list:
        cached = await self.cache.get_section(tenant_id, section)
        if cached is not None:
            return cached
        row = await self.session.get(TenantMemory, tenant_id)
        if row is None:
            raise MemoryNotBuiltError(tenant_id)
        value = getattr(row, section, None)
        if value is None:
            raise UnknownMemorySectionError(section)
        await self.cache.set_section(tenant_id, section, value, version=row.memory_version)
        return value

    # ── STALENESS ──
    async def mark_stale(self, tenant_id: str) -> None:
        row = await self.session.get(TenantMemory, tenant_id)
        if row is None:
            return
        row.stale = True
        await self.session.commit()
        await self.cache.patch(tenant_id, {"stale": True})
        logger.info("memory.mark_stale tenant=%s", tenant_id)

    async def is_stale(self, tenant_id: str, current_fingerprint: str) -> bool:
        row = await self.session.get(TenantMemory, tenant_id)
        if row is None or row.source_fingerprint is None:
            return False
        changed = row.source_fingerprint != current_fingerprint
        if changed:
            await self.mark_stale(tenant_id)
        return changed

    @staticmethod
    def fingerprint(raw_rows: dict) -> str:
        canonical = repr(sorted((k, len(v)) for k, v in raw_rows.items()))
        return hashlib.sha256(canonical.encode()).hexdigest()

    # ── REFRESH / INVALIDATE ──
    async def refresh(self, tenant_id: str, source_id: str) -> str:
        from app.services.sync import SyncService

        return await SyncService(self.session).start(tenant_id, source_id, kind="refresh")

    async def invalidate(self, tenant_id: str) -> None:
        await self.cache.invalidate(tenant_id)

    async def _warm_redis(self, tenant_id: str, payload: dict, *, version: int) -> None:
        try:
            await self.cache.invalidate(tenant_id)
            await self.cache.set_snapshot(
                tenant_id,
                payload | {"initialized": True, "stale": False, "memory_version": version},
                version=version,
            )
            for section in _SECTIONS:
                if section in payload:
                    await self.cache.set_section(
                        tenant_id, section, payload[section], version=version
                    )
        except Exception:  # noqa: BLE001 — Redis warm is best-effort; PG is the truth
            logger.warning(
                "memory._warm_redis failed tenant=%s (cache will lazily backfill)", tenant_id
            )
