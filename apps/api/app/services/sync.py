"""SyncService — orchestrate sync state. One running sync per tenant."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import SyncRun


class SyncAlreadyRunningError(Exception): ...


class SyncService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def start(self, tenant_id: str, source_id: str, *, kind: str) -> str:
        existing = await self.session.scalar(select(SyncRun).where(SyncRun.status == "running"))
        if existing:
            raise SyncAlreadyRunningError(str(existing.id))

        run = SyncRun(
            tenant_id=UUID(tenant_id), source_id=UUID(source_id), kind=kind, status="running"
        )
        self.session.add(run)
        await self.session.commit()

        from app.workers.sync_tasks import initial_sync, refresh_sync

        if kind == "refresh":
            async_result = refresh_sync.delay(tenant_id, source_id, str(run.id))
        else:
            async_result = initial_sync.delay(tenant_id, source_id, str(run.id))
        run.celery_task_id = str(async_result.id)
        await self.session.commit()
        return str(run.id)

    async def complete(self, sync_run_id: str) -> None:
        run = await self.session.get(SyncRun, UUID(sync_run_id))
        if run is None:
            return
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        await self.session.commit()

    async def fail(self, sync_run_id: str, error: str) -> None:
        run = await self.session.get(SyncRun, UUID(sync_run_id))
        if run is None:
            return
        run.status = "failed"
        run.error_message = error[:2000]
        run.completed_at = datetime.now(UTC)
        await self.session.commit()

    async def status(self, tenant_id: str) -> SyncRun | None:
        return await self.session.scalar(
            select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1)
        )
