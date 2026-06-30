"""Workflow tasks & approval gates (§5, §7). The approve/reject endpoints are the ONLY
human-in-the-loop authorization path: an external action fires solely via `/tasks/{id}/approve`.

Approval/rejection is role-gated (config: `workflow_approve_roles`). Illegal state transitions
→ 409; deciding an already-decided gate → 409.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.config import settings
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.automation import Task
from app.services.external_actions import UnapprovedActionError
from app.services.task import (
    GateAlreadyDecided,
    IllegalTaskTransition,
    TaskService,
)
from app.services.workflow import WorkflowService, _task_obj

router = APIRouter(tags=["tasks"])


class TaskCreate(BaseModel):
    type: str
    title: str
    opportunity_id: str | None = None
    priority: str = "normal"
    description: str | None = None


class TaskPatch(BaseModel):
    owner_id: str | None = None
    priority: str | None = None
    description: str | None = None


class StatusPatch(BaseModel):
    status: str


class Decision(BaseModel):
    note: str | None = None


def _require_approver(principal: Principal) -> None:
    """Approvals are restricted to the configured roles (defense beyond the permission)."""
    if principal.role not in settings.workflow_approve_roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"role '{principal.role}' may not approve workflow actions",
        )


@router.get("/tasks", dependencies=[Depends(require_permission("task:read"))])
async def list_tasks(
    status_filter: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(Task).order_by(Task.created_at.desc())
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    rows = (await session.scalars(stmt)).all()
    return {"tasks": [_task_obj(t) for t in rows]}


@router.post(
    "/tasks",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("task:write"))],
)
async def create_task(
    body: TaskCreate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = TaskService(session, principal.tenant_id)
    task = await svc.create(
        opportunity_id=body.opportunity_id,
        type=body.type,
        title=body.title,
        priority=body.priority,
        created_by="human",
    )
    if body.description:
        task.description = body.description
    await session.commit()
    return _task_obj(task)


@router.get("/tasks/{task_id}", dependencies=[Depends(require_permission("task:read"))])
async def get_task(
    task_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = TaskService(session, principal.tenant_id)
    task = await svc.get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    gate = await svc.pending_gate_for_task(task_id)
    body = _task_obj(task)
    body["pending_gate_id"] = str(gate.id) if gate else None
    return body


@router.patch("/tasks/{task_id}", dependencies=[Depends(require_permission("task:write"))])
async def patch_task(
    task_id: str,
    body: TaskPatch,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = TaskService(session, principal.tenant_id)
    task = await svc.get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    if body.owner_id is not None:
        await svc.assign(task_id, body.owner_id)
    if body.priority is not None:
        task.priority = body.priority
    if body.description is not None:
        task.description = body.description
    await session.commit()
    return _task_obj(task)


@router.patch(
    "/tasks/{task_id}/status", dependencies=[Depends(require_permission("task:write"))]
)
async def patch_status(
    task_id: str,
    body: StatusPatch,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = TaskService(session, principal.tenant_id)
    if await svc.get(task_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    try:
        await svc.set_status(task_id, body.status)
    except IllegalTaskTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return _task_obj(await svc.get(task_id))  # type: ignore[arg-type]


@router.post("/tasks/{task_id}/approve", dependencies=[Depends(require_permission("task:approve"))])
async def approve_task(
    task_id: str,
    body: Decision,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_approver(principal)
    svc = WorkflowService(session, principal.tenant_id)
    try:
        result = await svc.approve(task_id, decided_by=principal.user_id, note=body.note)
    except GateAlreadyDecided as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except UnapprovedActionError as exc:  # defense-in-depth guard tripped
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await session.commit()
    return result


@router.post("/tasks/{task_id}/reject", dependencies=[Depends(require_permission("task:approve"))])
async def reject_task(
    task_id: str,
    body: Decision,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_approver(principal)
    svc = WorkflowService(session, principal.tenant_id)
    try:
        result = await svc.reject(task_id, decided_by=principal.user_id, note=body.note)
    except GateAlreadyDecided as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await session.commit()
    return result
