"""Sync API: start initial/refresh syncs; report status + staleness + coverage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.memory import TenantMemory
from app.schemas.sync import (
    CoverageStats,
    SyncStartRequest,
    SyncStartResponse,
    SyncStatusResponse,
)
from app.services.sync import SyncAlreadyRunningError, SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


async def _start(kind: str, body: SyncStartRequest, principal: Principal, session: AsyncSession):
    svc = SyncService(session)
    try:
        sync_run_id = await svc.start(principal.tenant_id, body.source_id, kind=kind)
    except SyncAlreadyRunningError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"sync already running: {exc}") from exc
    from uuid import UUID

    from app.models.memory import SyncRun

    run = await session.get(SyncRun, UUID(sync_run_id))
    return SyncStartResponse(
        sync_run_id=sync_run_id,
        task_id=run.celery_task_id if run else None,
        kind=kind,
        status="running",
    )


@router.post(
    "/initial",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SyncStartResponse,
    dependencies=[Depends(require_permission("data_quality:write"))],
)
async def start_initial_sync(
    body: SyncStartRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> SyncStartResponse:
    return await _start("initial", body, principal, session)


@router.post(
    "/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SyncStartResponse,
    dependencies=[Depends(require_permission("data_quality:write"))],
)
async def start_refresh_sync(
    body: SyncStartRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> SyncStartResponse:
    return await _start("refresh", body, principal, session)


@router.get(
    "/status",
    response_model=SyncStatusResponse,
    dependencies=[Depends(require_permission("dashboard:read"))],
)
async def sync_status(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> SyncStatusResponse:
    sync = await SyncService(session).status(principal.tenant_id)
    from uuid import UUID

    mem = await session.get(TenantMemory, UUID(principal.tenant_id))
    if mem is None:
        return SyncStatusResponse(
            initialized=False,
            status=sync.status if sync else None,
            stage=sync.stage if sync else None,
            stale=False,
            last_synced_at=None,
            memory_version=None,
            coverage=None,
            error_message=sync.error_message if sync else None,
        )
    return SyncStatusResponse(
        initialized=True,
        status=sync.status if sync else "completed",
        stage=sync.stage if sync and sync.status == "running" else None,
        stale=mem.stale,
        last_synced_at=mem.last_synced_at,
        memory_version=mem.memory_version,
        coverage=CoverageStats(
            match_coverage_pct=mem.match_coverage_pct,
            spend_under_management_pct=mem.spend_under_management_pct,
            contract_count=mem.contract_count,
            opportunity_count=mem.opportunity_count,
        ),
        error_message=sync.error_message if sync else None,
    )
