"""Contracts read endpoints (§6.1) — list + detail + linked-spend drill-down."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.deps import get_read_models
from app.core.auth import Principal, get_current_principal
from app.core.rbac import require_permission
from app.schemas.read_models import (
    ContractDetail,
    ContractListResponse,
    ContractSpendResponse,
)
from app.services.read_models import ContractNotFoundError, ReadModelService

router = APIRouter(prefix="/contracts", tags=["contracts"])

_READ = Depends(require_permission("contract:read"))


@router.get("", response_model=ContractListResponse, dependencies=[_READ])
async def list_contracts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> ContractListResponse:
    return ContractListResponse(**await rms.contracts_list(principal.tenant_id, page, page_size))


@router.get("/{contract_id}", response_model=ContractDetail, dependencies=[_READ])
async def contract_detail(
    contract_id: str,
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> ContractDetail:
    try:
        return ContractDetail(**await rms.contract_detail(principal.tenant_id, contract_id))
    except ContractNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contract not found") from exc


@router.get("/{contract_id}/spend", response_model=ContractSpendResponse, dependencies=[_READ])
async def contract_spend(
    contract_id: str,
    principal: Principal = Depends(get_current_principal),
    rms: ReadModelService = Depends(get_read_models),
) -> ContractSpendResponse:
    return ContractSpendResponse(**await rms.contract_spend(principal.tenant_id, contract_id))
