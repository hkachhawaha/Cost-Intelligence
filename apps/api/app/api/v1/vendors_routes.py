"""Vendors module API (§6.1) — rollup + consolidation candidates."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.schemas.advanced import (
    ConsolidationCandidateOut,
    ConsolidationResponse,
    VendorListResponse,
    VendorRollupOut,
)
from app.services.vendors import vendor_service

router = APIRouter(prefix="/vendors", tags=["vendors"])
_READ = Depends(require_permission("vendor:read"))


@router.get("", response_model=VendorListResponse, dependencies=[_READ])
async def list_vendors(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> VendorListResponse:
    rows = await vendor_service.rollup(session, principal)
    return VendorListResponse(vendors=[VendorRollupOut(**r.__dict__) for r in rows])


@router.get("/consolidation-candidates", response_model=ConsolidationResponse, dependencies=[_READ])
async def consolidation_candidates(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> ConsolidationResponse:
    rows = await vendor_service.consolidation_candidates(session, principal)
    return ConsolidationResponse(candidates=[ConsolidationCandidateOut(**r.__dict__) for r in rows])
