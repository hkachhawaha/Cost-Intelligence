"""Data Quality read endpoints (§6.1) — coverage from memory + canonical event feed."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import get_read_models
from app.core.auth import Principal, get_current_principal
from app.core.rbac import require_permission
from app.schemas.read_models import DataQualityCoverage, DataQualityEventsResponse
from app.services.read_models import ReadModelService

router = APIRouter(prefix="/data-quality", tags=["data-quality"])

_READ = Depends(require_permission("data_quality:read"))


@router.get("/coverage", response_model=DataQualityCoverage, dependencies=[_READ])
async def dq_coverage(
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> DataQualityCoverage:
    return DataQualityCoverage(**await rms.dq_coverage(principal.tenant_id))


@router.get("/events", response_model=DataQualityEventsResponse, dependencies=[_READ])
async def dq_events(
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> DataQualityEventsResponse:
    return DataQualityEventsResponse(**await rms.dq_events(principal.tenant_id, limit))
