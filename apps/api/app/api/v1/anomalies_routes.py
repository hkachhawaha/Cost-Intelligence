"""Anomalies API (§6.5) — list/detail/run (statistical) + human review."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.advanced import AnomalyFlag
from app.schemas.advanced import (
    AnomalyListResponse,
    AnomalyOut,
    AnomalyReviewRequest,
    RunResponse,
)

router = APIRouter(prefix="/anomalies", tags=["anomalies"])
_READ = Depends(require_permission("data_quality:read"))
_WRITE = Depends(require_permission("data_quality:write"))


def _out(f: AnomalyFlag) -> AnomalyOut:
    return AnomalyOut(
        id=str(f.id),
        anomaly_type=f.anomaly_type,
        subject_type=f.subject_type,
        subject_id=str(f.subject_id),
        method=f.method,
        score=f.score,
        status=f.status,
        detail=f.detail,
    )


@router.get("", response_model=AnomalyListResponse, dependencies=[_READ])
async def list_anomalies(
    anomaly_type: str | None = Query(None, alias="type"),
    status_filter: str | None = Query(None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> AnomalyListResponse:
    conds = []
    if anomaly_type:
        conds.append(AnomalyFlag.anomaly_type == anomaly_type)
    if status_filter:
        conds.append(AnomalyFlag.status == status_filter)
    rows = (
        await session.scalars(
            select(AnomalyFlag).where(*conds).order_by(desc(AnomalyFlag.created_at))
        )
    ).all()
    return AnomalyListResponse(anomalies=[_out(f) for f in rows])


@router.post(
    "/run", status_code=status.HTTP_202_ACCEPTED, response_model=RunResponse, dependencies=[_WRITE]
)
async def run_detection(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    """Assemble spend series from the canonical store and run the statistical detectors
    (no LLM). Persists pending flags."""
    from collections import defaultdict
    from decimal import Decimal

    from app.agents.anomaly import anomaly_graph
    from app.core.agent_run import agent_run

    rows = (
        (
            await session.execute(
                text("SELECT id, vendor_id, gl_code, amount, spend_date FROM spend_records")
            )
        )
        .mappings()
        .all()
    )

    series_by_vendor: dict[str, list] = defaultdict(list)
    by_gl: dict[str, list] = defaultdict(list)
    payment_records: list[dict] = []
    for r in rows:
        series_by_vendor[str(r["vendor_id"])].append((str(r["id"]), Decimal(str(r["amount"]))))
        if r["gl_code"]:
            by_gl[r["gl_code"]].append((str(r["id"]), Decimal(str(r["amount"]))))
        payment_records.append(
            {
                "spend_id": r["id"],
                "vendor_id": r["vendor_id"],
                "amount": Decimal(str(r["amount"])),
                "spend_date": r["spend_date"],
            }
        )
    current_vendors = {str(r["vendor_id"]) for r in rows}

    async with agent_run(
        tenant_id=principal.tenant_id, agent="anomaly", trigger="user_request"
    ) as run:
        out = await anomaly_graph.ainvoke(
            {
                "tenant_id": principal.tenant_id,
                "run_id": str(run.run_id),
                "series_by_vendor": dict(series_by_vendor),
                "by_gl": dict(by_gl),
                "current_vendors": current_vendors,
                "historical_vendors": set(),
                "payment_records": payment_records,
            }
        )
        run.set_outputs({"flags": len(out.get("flags", []))})
    return RunResponse(status="completed", detail={"flags": len(out.get("flags", []))})


@router.patch("/{flag_id}/review", dependencies=[_WRITE])
async def review_anomaly(
    flag_id: str,
    body: AnomalyReviewRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    flag = await session.get(AnomalyFlag, UUID(flag_id))
    if flag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "anomaly not found")
    if flag.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "anomaly already reviewed")
    flag.status = "dismissed" if body.action == "dismiss" else "promoted_to_opportunity"
    flag.reviewed_by = UUID(principal.user_id)
    await record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        event_type=f"anomaly.{body.action}",
        actor="human",
        actor_user_id=UUID(principal.user_id),
        payload={"flag_id": flag_id, "anomaly_type": flag.anomaly_type},
        run_id=flag.run_id,
    )
    await session.commit()
    return {"id": flag_id, "status": flag.status}
