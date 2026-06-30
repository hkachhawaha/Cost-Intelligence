"""Quarantine queue + resolve."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.staging import StagedRecord
from app.schemas.data_sources import QuarantineItem, ResolveQuarantineRequest

router = APIRouter(prefix="/staging")


@router.get(
    "/quarantine",
    response_model=list[QuarantineItem],
    dependencies=[Depends(require_permission("data_quality:read"))],
)
async def list_quarantine(
    status_filter: str = "pending", session: AsyncSession = Depends(get_session)
) -> list[QuarantineItem]:
    rows = (
        (await session.execute(select(StagedRecord).where(StagedRecord.status == status_filter)))
        .scalars()
        .all()
    )
    return [
        QuarantineItem(
            id=r.id,
            record_type=r.record_type,
            raw_data=r.raw_data,
            validation_errors=r.validation_errors,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post(
    "/quarantine/{staged_id}/resolve",
    dependencies=[Depends(require_permission("data_quality:write"))],
)
async def resolve_quarantine(
    staged_id: UUID,
    body: ResolveQuarantineRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rec = await session.get(StagedRecord, staged_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "staged record not found")
    # Run synchronously through the same logic the worker uses.
    from app.workers.ingestion_tasks import process_quarantine_async

    try:
        result = await process_quarantine_async(
            principal.tenant_id, str(staged_id), body.action, body.patch
        )
    except Exception as exc:  # noqa: BLE001 — still-invalid fix → 422
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return result
