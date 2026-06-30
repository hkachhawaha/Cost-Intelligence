"""Agent Memory layer. Persists the built intelligence as a versioned JSONB snapshot
(durable in Postgres) and warms a Redis copy for fast reads. The app and NirvanAI read the
latest snapshot — never the live sheet — until a Refresh writes a new version.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost_intelligence import CiDataSource, CiMemorySnapshot

logger = logging.getLogger("ci.memory")

_REDIS_KEY = "ci:memory:latest"


class AgentMemory:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def store(self, *, spreadsheet_id: str, url: str, name: str | None, payload: dict) -> int:
        """Upsert the data-source config and write a new memory snapshot version; warm Redis."""
        ds = await self.session.scalar(
            select(CiDataSource).where(CiDataSource.spreadsheet_id == spreadsheet_id)
        )
        total = sum(
            len(payload.get(k, []))
            for k in ("contracts", "invoices", "purchaseOrders", "inventory", "clauses", "spend")
        )
        now = datetime.now(UTC)
        if ds is None:
            ds = CiDataSource(id=uuid4(), spreadsheet_id=spreadsheet_id, spreadsheet_url=url)
            self.session.add(ds)
        ds.spreadsheet_url = url
        ds.spreadsheet_name = name or ds.spreadsheet_name
        ds.status = "connected"
        ds.last_synced_at = now
        ds.total_records = total
        ds.last_error = None

        next_version = (
            await self.session.scalar(select(func.coalesce(func.max(CiMemorySnapshot.version), 0)))
            or 0
        ) + 1
        payload = {
            **payload,
            "version": next_version,
            "syncedAt": now.isoformat(),
            "spreadsheetId": spreadsheet_id,
            "spreadsheetName": ds.spreadsheet_name,
            "totalRecords": total,
        }
        self.session.add(CiMemorySnapshot(id=uuid4(), version=next_version, payload=payload))
        await self.session.flush()
        await self._warm_redis(payload)
        logger.info("ci.memory.stored version=%d records=%d", next_version, total)
        return next_version

    async def mark_error(self, *, spreadsheet_id: str, url: str, error: str) -> None:
        ds = await self.session.scalar(
            select(CiDataSource).where(CiDataSource.spreadsheet_id == spreadsheet_id)
        )
        if ds is None:
            ds = CiDataSource(id=uuid4(), spreadsheet_id=spreadsheet_id, spreadsheet_url=url)
            self.session.add(ds)
        ds.status = "error"
        ds.last_error = error[:2000]
        await self.session.flush()

    async def data_source(self) -> CiDataSource | None:
        return await self.session.scalar(
            select(CiDataSource).order_by(CiDataSource.updated_at.desc()).limit(1)
        )

    async def latest(self) -> dict | None:
        """Latest snapshot payload — Redis first, then Postgres."""
        cached = await self._read_redis()
        if cached is not None:
            return cached
        row = await self.session.scalar(
            select(CiMemorySnapshot).order_by(CiMemorySnapshot.version.desc()).limit(1)
        )
        return row.payload if row else None

    # ── Redis warm cache (best-effort) ────────────────────────────────────────
    async def _warm_redis(self, payload: dict) -> None:
        try:
            from app.core.redis import get_redis

            r = get_redis()
            await r.set(_REDIS_KEY, json.dumps(payload, default=str))
            await r.aclose()
        except Exception as exc:  # noqa: BLE001 — cache is best-effort; Postgres is the source
            logger.warning("ci.memory.redis_warm_failed err=%s", exc)

    async def _read_redis(self) -> dict | None:
        try:
            from app.core.redis import get_redis

            r = get_redis()
            raw = await r.get(_REDIS_KEY)
            await r.aclose()
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            return None
