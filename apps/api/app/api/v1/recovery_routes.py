"""Margin Recovery read endpoints (§6.1) — recovery_items grouped into packs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.deps import get_read_models
from app.core.auth import Principal, get_current_principal
from app.core.rbac import require_permission
from app.schemas.read_models import RecoveryPack, RecoveryPacksResponse
from app.services.read_models import ContractNotFoundError, ReadModelService

router = APIRouter(prefix="/recovery", tags=["recovery"])

_READ = Depends(require_permission("recovery:read"))


@router.get("/packs", response_model=RecoveryPacksResponse, dependencies=[_READ])
async def recovery_packs(
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> RecoveryPacksResponse:
    return RecoveryPacksResponse(**await rms.recovery_packs(principal.tenant_id))


@router.get("/{rec_id}", response_model=RecoveryPack, dependencies=[_READ])
async def recovery_pack(
    rec_id: str,
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> RecoveryPack:
    try:
        return RecoveryPack(**await rms.recovery_pack(principal.tenant_id, rec_id))
    except ContractNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recovery item not found") from exc
