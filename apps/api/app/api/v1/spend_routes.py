"""Spend Explorer read endpoints (§6.1) — memory sections only."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_read_models
from app.core.auth import Principal, get_current_principal
from app.core.rbac import require_permission
from app.schemas.read_models import (
    MatchCoverageResponse,
    SpendBreakdownResponse,
    SpendTrendResponse,
)
from app.services.read_models import ReadModelService

router = APIRouter(prefix="/spend", tags=["spend"])

_READ = Depends(require_permission("spend:read"))


@router.get("/by-vendor", response_model=SpendBreakdownResponse, dependencies=[_READ])
async def by_vendor(
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> SpendBreakdownResponse:
    return SpendBreakdownResponse(**await rms.spend_by(principal.tenant_id, "vendor"))


@router.get("/by-category", response_model=SpendBreakdownResponse, dependencies=[_READ])
async def by_category(
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> SpendBreakdownResponse:
    return SpendBreakdownResponse(**await rms.spend_by(principal.tenant_id, "category"))


@router.get("/by-cost-center", response_model=SpendBreakdownResponse, dependencies=[_READ])
async def by_cost_center(
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> SpendBreakdownResponse:
    return SpendBreakdownResponse(**await rms.spend_by(principal.tenant_id, "cost-center"))


@router.get("/trend", response_model=SpendTrendResponse, dependencies=[_READ])
async def trend(
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> SpendTrendResponse:
    return SpendTrendResponse(**await rms.spend_trend(principal.tenant_id))


@router.get("/match-coverage", response_model=MatchCoverageResponse, dependencies=[_READ])
async def match_coverage(
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> MatchCoverageResponse:
    return MatchCoverageResponse(**await rms.match_coverage(principal.tenant_id))
