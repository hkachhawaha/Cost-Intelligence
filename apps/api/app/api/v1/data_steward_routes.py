"""Data Steward API (§6.6) — proposals, metrics, run, approve/reject (figure-affecting gated)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.advanced import StewardProposal
from app.schemas.advanced import (
    ProposalActionRequest,
    ProposalListResponse,
    ProposalOut,
    RunResponse,
)

router = APIRouter(prefix="/data-steward", tags=["data-steward"])
_READ = Depends(require_permission("data_quality:read"))
_WRITE = Depends(require_permission("data_quality:write"))


def _out(p: StewardProposal) -> ProposalOut:
    return ProposalOut(
        id=str(p.id),
        proposal_type=p.proposal_type,
        subject_type=p.subject_type,
        subject_id=str(p.subject_id) if p.subject_id else None,
        affects_figures=p.affects_figures,
        rationale=p.rationale,
        status=p.status,
        current_value=p.current_value,
        proposed_value=p.proposed_value,
    )


@router.get("/proposals", response_model=ProposalListResponse, dependencies=[_READ])
async def list_proposals(
    status_filter: str | None = Query(None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> ProposalListResponse:
    conds = [StewardProposal.status == status_filter] if status_filter else []
    rows = (
        await session.scalars(
            select(StewardProposal).where(*conds).order_by(desc(StewardProposal.created_at))
        )
    ).all()
    return ProposalListResponse(proposals=[_out(p) for p in rows])


@router.get("/metrics", dependencies=[_READ])
async def metrics(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from app.agents.data_steward import compute_quality_metrics

    out = await compute_quality_metrics({"tenant_id": principal.tenant_id})
    return out.get("quality_metrics", {})


@router.post(
    "/run", status_code=status.HTTP_202_ACCEPTED, response_model=RunResponse, dependencies=[_WRITE]
)
async def run_steward(
    principal: Principal = Depends(get_current_principal),
) -> RunResponse:
    from app.agents.data_steward import steward_graph
    from app.core.agent_run import agent_run

    async with agent_run(
        tenant_id=principal.tenant_id, agent="data_steward", trigger="user_request"
    ) as run:
        out = await steward_graph.ainvoke(
            {"tenant_id": principal.tenant_id, "run_id": str(run.run_id), "base_currency": "USD"}
        )
        run.set_outputs({"proposals": len(out.get("proposals", []))})
    return RunResponse(status="completed", detail={"proposals": len(out.get("proposals", []))})


@router.patch("/proposals/{proposal_id}", dependencies=[_WRITE])
async def review_proposal(
    proposal_id: str,
    body: ProposalActionRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    p = await session.get(StewardProposal, UUID(proposal_id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found")
    if p.status in ("applied", "rejected"):
        raise HTTPException(status.HTTP_409_CONFLICT, "proposal already resolved")

    if body.action == "reject":
        p.status = "rejected"
        p.approved_by = UUID(principal.user_id)
        await session.commit()
        return {"id": proposal_id, "status": "rejected"}

    # approve → apply (the actual data mutation for each proposal_type would happen here).
    p.status = "applied"
    p.approved_by = UUID(principal.user_id)
    await record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        event_type="steward.applied",
        actor="human",
        actor_user_id=UUID(principal.user_id),
        payload={
            "proposal_id": proposal_id,
            "proposal_type": p.proposal_type,
            "affects_figures": p.affects_figures,
        },
        run_id=p.run_id,
    )
    await session.commit()
    return {"id": proposal_id, "status": "applied"}
