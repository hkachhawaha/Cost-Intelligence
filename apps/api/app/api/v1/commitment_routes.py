"""Commitment Check API (§6.1). Pre-signature stress test → approve/condition/block verdict
(advisory). Role-gated to `commitment_required_roles`. Sign-off records a human decision; the
platform never signs. A second sign-off → 409 (the decision is immutable).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.config import settings
from app.core.database import get_session
from app.core.rbac import require_permission
from app.schemas.commitment import ProposedDeal, SignDecision
from app.services.commitment import AlreadySigned, CommitmentCheckService, commitment_obj

router = APIRouter(prefix="/commitment-check", tags=["commitment"])


def _require_commitment_role(principal: Principal) -> None:
    if principal.role not in settings.commitment_required_roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"role '{principal.role}' may not run commitment checks",
        )


@router.post("", dependencies=[Depends(require_permission("commitment:write"))])
async def run_check(
    deal: ProposedDeal,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_commitment_role(principal)
    svc = CommitmentCheckService(session, principal.tenant_id)
    check = await svc.run(deal, requested_by=principal.user_id)
    await session.commit()
    return commitment_obj(check)


@router.get("", dependencies=[Depends(require_permission("commitment:read"))])
async def list_checks(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = CommitmentCheckService(session, principal.tenant_id)
    return {"checks": [commitment_obj(c) for c in await svc.list()]}


@router.get("/{check_id}", dependencies=[Depends(require_permission("commitment:read"))])
async def get_check(
    check_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = CommitmentCheckService(session, principal.tenant_id)
    check = await svc.get(check_id)
    if check is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "commitment check not found")
    return commitment_obj(check)


@router.post("/{check_id}/sign", dependencies=[Depends(require_permission("commitment:write"))])
async def sign_check(
    check_id: str,
    body: SignDecision,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_commitment_role(principal)
    svc = CommitmentCheckService(session, principal.tenant_id)
    try:
        check = await svc.sign(
            check_id, decision=body.decision, signed_by=principal.user_id, note=body.note
        )
    except AlreadySigned as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await session.commit()
    return commitment_obj(check)
