"""RedisKpiCache — versioned Redis cache for the tenant KPI snapshot (Store 3).

Keys: `kpis:{tenant}` (full snapshot), `section:{tenant}:{name}` (per-section),
`memver:{tenant}` (version). Postgres `tenant_memory` is the source of truth; this
cache is derived and disposable — a flush only costs a re-warm on the next read.
"""

from __future__ import annotations

import json
from decimal import Decimal

from redis.asyncio import Redis

from app.core.config import settings


def _default(o):
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(f"not serializable: {type(o)}")


class RedisKpiCache:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.ttl = settings.memory_cache_ttl_seconds

    def _kpis_key(self, t: str) -> str:
        return f"kpis:{t}"

    def _section_key(self, t: str, s: str) -> str:
        return f"section:{t}:{s}"

    def _ver_key(self, t: str) -> str:
        return f"memver:{t}"

    async def get_snapshot(self, tenant_id: str) -> dict | None:
        raw = await self.redis.get(self._kpis_key(tenant_id))
        return json.loads(raw) if raw else None

    async def set_snapshot(self, tenant_id: str, payload: dict, *, version: int) -> None:
        pipe = self.redis.pipeline()
        pipe.set(self._kpis_key(tenant_id), json.dumps(payload, default=_default), ex=self.ttl)
        pipe.set(self._ver_key(tenant_id), version, ex=self.ttl)
        await pipe.execute()

    async def get_section(self, tenant_id: str, section: str) -> dict | list | None:
        raw = await self.redis.get(self._section_key(tenant_id, section))
        return json.loads(raw) if raw else None

    async def set_section(self, tenant_id: str, section: str, value, *, version: int) -> None:
        await self.redis.set(
            self._section_key(tenant_id, section), json.dumps(value, default=_default), ex=self.ttl
        )

    async def patch(self, tenant_id: str, fields: dict) -> None:
        snap = await self.get_snapshot(tenant_id)
        if snap is None:
            return
        snap.update(fields)
        ver = int(await self.redis.get(self._ver_key(tenant_id)) or 1)
        await self.set_snapshot(tenant_id, snap, version=ver)

    async def invalidate(self, tenant_id: str) -> None:
        keys = [self._kpis_key(tenant_id), self._ver_key(tenant_id)]
        async for key in self.redis.scan_iter(match=f"section:{tenant_id}:*"):
            keys.append(key)
        if keys:
            await self.redis.delete(*keys)
