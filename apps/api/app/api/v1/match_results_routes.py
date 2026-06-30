"""Match-results API: list, detail, accept, reassign, rematch, unmatched queue."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.matching import MatchResult, UnmatchedQueue
from app.schemas.matching import (
    MatchResultList,
    MatchResultOut,
    ReassignMatchRequest,
    RematchRequest,
    RematchResponse,
    UnmatchedOut,
)
from app.services.matching import MatchingService
from app.services.matching_candidates import CandidateRetrievalService

router = APIRouter(prefix="/match-results", tags=["matching"])


def _out(mr: MatchResult) -> MatchResultOut:
    return MatchResultOut.model_validate(mr, from_attributes=True)


@router.get(
    "",
    response_model=MatchResultList,
    dependencies=[Depends(require_permission("data_quality:read"))],
)
async def list_match_results(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    confidence_gte: float | None = None,
    confidence_lte: float | None = None,
    method: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> MatchResultList:
    conds = []
    if confidence_gte is not None:
        conds.append(MatchResult.confidence >= confidence_gte)
    if confidence_lte is not None:
        conds.append(MatchResult.confidence <= confidence_lte)
    if method:
        conds.append(MatchResult.method == method)
    if status_filter:
        conds.append(MatchResult.status == status_filter)

    total = (
        await session.execute(select(func.count()).select_from(MatchResult).where(*conds))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(MatchResult)
                .where(*conds)
                .order_by(MatchResult.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )
    return MatchResultList(
        items=[_out(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get(
    "/unmatched",
    response_model=list[UnmatchedOut],
    dependencies=[Depends(require_permission("data_quality:read"))],
)
async def list_unmatched(session: AsyncSession = Depends(get_session)) -> list[UnmatchedOut]:
    rows = (
        (await session.execute(select(UnmatchedQueue).where(UnmatchedQueue.status == "pending")))
        .scalars()
        .all()
    )
    return [UnmatchedOut.model_validate(r, from_attributes=True) for r in rows]


@router.get(
    "/{match_id}",
    response_model=MatchResultOut,
    dependencies=[Depends(require_permission("data_quality:read"))],
)
async def get_match_result(
    match_id: UUID, session: AsyncSession = Depends(get_session)
) -> MatchResultOut:
    mr = await session.get(MatchResult, match_id)
    if mr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match result not found")
    return _out(mr)


@router.patch(
    "/{match_id}/reassign",
    response_model=MatchResultOut,
    dependencies=[Depends(require_permission("data_quality:write"))],
)
async def reassign_match(
    match_id: UUID,
    body: ReassignMatchRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> MatchResultOut:
    svc = MatchingService(session, CandidateRetrievalService(session))
    try:
        mr = await svc.accept_human_match(match_id, principal, body.contract_id, body.reason)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await session.commit()
    return _out(mr)


@router.patch(
    "/{match_id}/accept",
    response_model=MatchResultOut,
    dependencies=[Depends(require_permission("data_quality:write"))],
)
async def accept_match(
    match_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> MatchResultOut:
    mr = await session.get(MatchResult, match_id)
    if mr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match result not found")
    svc = MatchingService(session, CandidateRetrievalService(session))
    updated = await svc.accept_human_match(
        match_id, principal, mr.contract_id, "accepted by reviewer"
    )
    await session.commit()
    return _out(updated)


@router.post(
    "/rematch",
    response_model=RematchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("data_quality:write"))],
)
async def rematch(
    body: RematchRequest,
    principal: Principal = Depends(get_current_principal),
) -> RematchResponse:
    from app.workers.matching_tasks import rematch_unmatched

    async_result = rematch_unmatched.delay(principal.tenant_id, body.scope)
    return RematchResponse(task_id=str(async_result.id), scope=body.scope)
