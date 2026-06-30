"""Renewals read endpoint (§6.1) — windowed memory renewal_calendar."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import get_read_models
from app.core.auth import Principal, get_current_principal
from app.core.rbac import require_permission
from app.schemas.read_models import RenewalsResponse
from app.services.read_models import ReadModelService

router = APIRouter(prefix="/renewals", tags=["renewals"])


@router.get(
    "",
    response_model=RenewalsResponse,
    dependencies=[Depends(require_permission("renewal:read"))],
)
async def get_renewals(
    window: int = Query(90),
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> RenewalsResponse:
    if window not in (90, 180, 365):
        raise HTTPException(422, "window must be 90, 180, or 365")
    return RenewalsResponse(**await rms.renewals(principal.tenant_id, window))
