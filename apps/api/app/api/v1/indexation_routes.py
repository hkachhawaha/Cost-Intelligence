"""Indexation & Exposure module API (§6.2) — register + first-party exposure slider."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.advanced import IndexRegisterEntry
from app.schemas.advanced import ExposureLineOut, ExposureResponse, IndexRegisterPut
from app.services.indexation import indexation_service

router = APIRouter(prefix="/indexation", tags=["indexation"])
_READ = Depends(require_permission("indexation:read"))


@router.get("/register", dependencies=[_READ])
async def register(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return {"register": await indexation_service.register(session, principal)}


@router.get("/exposure", response_model=ExposureResponse, dependencies=[_READ])
async def exposure(
    move_pct: Decimal = Query(..., ge=0, le=100),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> ExposureResponse:
    result = await indexation_service.exposure(session, principal, move_pct=move_pct)
    return ExposureResponse(
        assumed_move_pct=result.assumed_move_pct,
        total_indexed_exposure=result.total_indexed_exposure,
        lines=[ExposureLineOut(**ln.__dict__) for ln in result.lines],
    )


@router.put("/register/{contract_id}", dependencies=[Depends(require_permission("contract:write"))])
async def set_register(
    contract_id: str,
    body: IndexRegisterPut,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    cid = UUID(contract_id)
    # The contract must exist for this tenant (RLS-scoped) before registering an index entry.
    from app.models.contract import Contract

    if await session.get(Contract, cid) is None:
        raise HTTPException(404, "contract not found")
    existing = await session.scalar(
        select(IndexRegisterEntry).where(IndexRegisterEntry.contract_id == cid)
    )
    if existing:
        existing.index_type = body.index_type
        existing.indexed_share = float(body.indexed_share)
        existing.notes = body.notes
    else:
        session.add(
            IndexRegisterEntry(
                id=uuid4(),
                tenant_id=UUID(principal.tenant_id),
                contract_id=cid,
                index_type=body.index_type,
                indexed_share=float(body.indexed_share),
                notes=body.notes,
            )
        )
    await session.commit()
    return {
        "contract_id": contract_id,
        "index_type": body.index_type,
        "indexed_share": str(body.indexed_share),
    }
