"""Agent-runs API — the immutable audit log (paginated/filterable)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.agent_run import AgentRun
from app.schemas.sync import AgentRunListResponse, AgentRunOut

router = APIRouter(prefix="/agent-runs", tags=["audit"])


@router.get(
    "",
    response_model=AgentRunListResponse,
    dependencies=[Depends(require_permission("dashboard:read"))],
)
async def list_agent_runs(
    agent: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    actor: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> AgentRunListResponse:
    conds = []
    if agent:
        conds.append(AgentRun.agent == agent)
    if status_filter:
        conds.append(AgentRun.status == status_filter)
    if actor:
        conds.append(AgentRun.actor == actor)

    total = (
        await session.execute(select(func.count()).select_from(AgentRun).where(*conds))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(AgentRun)
                .where(*conds)
                .order_by(AgentRun.started_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )
    return AgentRunListResponse(
        items=[AgentRunOut.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{run_id}",
    response_model=AgentRunOut,
    dependencies=[Depends(require_permission("dashboard:read"))],
)
async def get_agent_run(run_id: UUID, session: AsyncSession = Depends(get_session)) -> AgentRunOut:
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent run not found")
    return AgentRunOut.model_validate(run, from_attributes=True)
