"""Dashboard read endpoint (§6.1) — single memory payload, no source query."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_read_models
from app.core.auth import Principal, get_current_principal
from app.core.rbac import require_permission
from app.schemas.read_models import DashboardKpis
from app.services.read_models import ReadModelService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/kpis",
    response_model=DashboardKpis,
    dependencies=[Depends(require_permission("dashboard:read"))],
)
async def get_dashboard_kpis(
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> DashboardKpis:
    payload = await rms.dashboard_kpis(principal.tenant_id)
    return DashboardKpis(**payload)
