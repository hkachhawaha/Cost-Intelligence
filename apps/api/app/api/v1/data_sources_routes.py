"""Data-sources CRUD + refresh + batches."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.oauth import build_consent_url, sign_state
from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.staging import DataSource, IngestionBatch
from app.schemas.data_sources import (
    CreateDataSourceRequest,
    DataSourceResponse,
    IngestionBatchResponse,
    RefreshResponse,
)

router = APIRouter(prefix="/data-sources")


def _to_response(ds: DataSource, oauth_url: str | None = None) -> DataSourceResponse:
    return DataSourceResponse(
        id=ds.id,
        name=ds.name,
        source_type=ds.source_type,
        status=ds.status,
        last_synced_at=ds.last_synced_at,
        last_error=ds.last_error,
        oauth_url=oauth_url,
    )


@router.get(
    "",
    response_model=list[DataSourceResponse],
    dependencies=[Depends(require_permission("data_quality:read"))],
)
async def list_sources(session: AsyncSession = Depends(get_session)) -> list[DataSourceResponse]:
    rows = (await session.execute(select(DataSource))).scalars().all()
    return [_to_response(d) for d in rows]


@router.post(
    "",
    response_model=DataSourceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("data_quality:write"))],
)
async def create_source(
    body: CreateDataSourceRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> DataSourceResponse:
    ds = DataSource(
        tenant_id=UUID(principal.tenant_id),
        name=body.name,
        source_type=body.source_type,
        config={
            "spreadsheet_id": body.spreadsheet_id,
            "ranges": body.ranges or {},
            "column_mappings": {
                k: [m.model_dump() for m in v] for k, v in body.column_mappings.items()
            },
        },
        status="pending",
    )
    session.add(ds)
    await session.flush()

    oauth_url = None
    if body.source_type == "google_sheets":
        state = sign_state(principal.tenant_id, str(ds.id), uuid4().hex)
        oauth_url = build_consent_url(state)
    await session.commit()
    return _to_response(ds, oauth_url)


@router.get(
    "/{source_id}",
    response_model=DataSourceResponse,
    dependencies=[Depends(require_permission("data_quality:read"))],
)
async def get_source(
    source_id: UUID, session: AsyncSession = Depends(get_session)
) -> DataSourceResponse:
    ds = await session.get(DataSource, source_id)
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "data source not found")
    return _to_response(ds)


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("admin"))],
)
async def delete_source(source_id: UUID, session: AsyncSession = Depends(get_session)) -> None:
    ds = await session.get(DataSource, source_id)
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "data source not found")
    await session.delete(ds)
    await session.commit()


@router.post(
    "/{source_id}/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("data_quality:write"))],
)
async def refresh_source(
    source_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> RefreshResponse:
    ds = await session.get(DataSource, source_id)
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "data source not found")
    if ds.status not in ("connected", "error"):
        raise HTTPException(status.HTTP_409_CONFLICT, "data source is not connected")
    # Enqueue async ingestion (Celery). Import here to avoid a hard worker dep at import.
    from app.workers.ingestion_tasks import refresh_source as refresh_task

    async_result = refresh_task.delay(principal.tenant_id, str(source_id))
    return RefreshResponse(task_id=str(async_result.id))


@router.get(
    "/{source_id}/batches",
    response_model=list[IngestionBatchResponse],
    dependencies=[Depends(require_permission("data_quality:read"))],
)
async def list_batches(
    source_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[IngestionBatchResponse]:
    rows = (
        (
            await session.execute(
                select(IngestionBatch)
                .where(IngestionBatch.source_id == source_id)
                .order_by(IngestionBatch.started_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        IngestionBatchResponse(
            id=b.id,
            dataset_type=b.dataset_type,
            status=b.status,
            record_count=b.record_count,
            inserted_count=b.inserted_count,
            updated_count=b.updated_count,
            error_count=b.error_count,
            started_at=b.started_at,
            completed_at=b.completed_at,
        )
        for b in rows
    ]
