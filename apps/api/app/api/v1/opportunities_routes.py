"""Opportunities API: ranked list, detail, status transitions, assign, run detection."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.opportunity import Opportunity
from app.schemas.opportunity import (
    AssignPatch,
    OpportunityDetail,
    OpportunityList,
    OpportunityOut,
    StatusPatch,
)
from app.services.opportunity_status import IllegalTransition, OpportunityStatusService

router = APIRouter(prefix="/opportunities", tags=["detection"])


def _out(o: Opportunity) -> OpportunityOut:
    return OpportunityOut.model_validate(o, from_attributes=True)


@router.get(
    "",
    response_model=OpportunityList,
    dependencies=[Depends(require_permission("opportunity:read"))],
)
async def list_opportunities(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    bucket: str | None = None,
    type_filter: str | None = Query(None, alias="type"),
    status_filter: str | None = Query(None, alias="status"),
    owner_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> OpportunityList:
    conds = []
    if bucket:
        conds.append(Opportunity.bucket == bucket)
    if type_filter:
        conds.append(Opportunity.type == type_filter)
    if status_filter:
        conds.append(Opportunity.status == status_filter)
    if owner_id:
        conds.append(Opportunity.owner_id == owner_id)

    total = (
        await session.execute(select(func.count()).select_from(Opportunity).where(*conds))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(Opportunity)
                .where(*conds)
                .order_by(Opportunity.rank_score.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )

    # Code-computed bucket totals (live, non-terminal opportunities).
    totals_rows = (
        await session.execute(
            select(Opportunity.bucket, func.coalesce(func.sum(Opportunity.impact), 0))
            .where(Opportunity.status.notin_(("dismissed",)))
            .group_by(Opportunity.bucket)
        )
    ).all()
    totals = {"savings": Decimal("0"), "recovery": Decimal("0"), "control": Decimal("0")}
    for bkt, amt in totals_rows:
        totals[bkt] = Decimal(str(amt))
    totals_out = {k: str(v) for k, v in totals.items()}
    totals_out["grand_total"] = str(totals["savings"] + totals["recovery"])

    return OpportunityList(
        items=[_out(o) for o in rows],
        total=total,
        page=page,
        page_size=page_size,
        totals=totals_out,
    )


@router.get(
    "/{opp_id}",
    response_model=OpportunityDetail,
    dependencies=[Depends(require_permission("opportunity:read"))],
)
async def get_opportunity(
    opp_id: UUID, session: AsyncSession = Depends(get_session)
) -> OpportunityDetail:
    opp = await session.get(Opportunity, opp_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "opportunity not found")
    return OpportunityDetail.model_validate(opp, from_attributes=True)


@router.patch(
    "/{opp_id}/status",
    response_model=OpportunityOut,
    dependencies=[Depends(require_permission("opportunity:write"))],
)
async def patch_status(
    opp_id: UUID,
    body: StatusPatch,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> OpportunityOut:
    opp = await session.get(Opportunity, opp_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "opportunity not found")
    svc = OpportunityStatusService(session)
    try:
        updated = await svc.transition(
            opp,
            body.status,
            principal,
            dismiss_reason=body.dismiss_reason,
            realized_amount=body.realized_amount,
        )
    except IllegalTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return _out(updated)


@router.patch(
    "/{opp_id}/assign",
    response_model=OpportunityOut,
    dependencies=[Depends(require_permission("opportunity:write"))],
)
async def assign_owner(
    opp_id: UUID,
    body: AssignPatch,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> OpportunityOut:
    opp = await session.get(Opportunity, opp_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "opportunity not found")
    svc = OpportunityStatusService(session)
    updated = await svc.assign(opp, body.owner_id, principal)
    await session.commit()
    return _out(updated)


detection_router = APIRouter(prefix="/detection", tags=["detection"])


@detection_router.post(
    "/run",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("opportunity:read"))],
)
async def run_detection_endpoint(
    principal: Principal = Depends(get_current_principal),
) -> dict:
    from app.workers.detection_tasks import run_detection

    async_result = run_detection.delay(principal.tenant_id, "user_request")
    return {"task_id": str(async_result.id), "tenant_id": principal.tenant_id}
