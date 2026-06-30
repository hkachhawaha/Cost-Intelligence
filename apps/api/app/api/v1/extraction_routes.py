"""Contract Extraction API (§6.4) — run extraction (async) + human verification queue.

Extraction NEVER auto-commits: the agent's terminal state is the verification queue. Only
a human `promote` writes verified fields to the canonical Contract (+ AuditEvent). Verify
is gated to the configured roles (legal/admin)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.auth import Principal, get_current_principal
from app.core.config import settings
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.advanced import ExtractionQueueItem
from app.models.contract import Contract
from app.schemas.advanced import (
    ExtractionItemOut,
    ExtractionListResponse,
    RunResponse,
    VerifyRequest,
)

router = APIRouter(tags=["extraction"])

# Which extracted keys may be promoted to canonical Contract, and how to coerce them.
_DECIMAL_FIELDS = {"acv", "tcv", "uplift_pct", "indexed_share"}
_DATE_FIELDS = {"start_date", "end_date"}
_INT_FIELDS = {"renewal_notice_days"}
_STR_FIELDS = {"renewal_type", "index_type"}
_PROMOTABLE = _DECIMAL_FIELDS | _DATE_FIELDS | _INT_FIELDS | _STR_FIELDS


def _coerce(key: str, value):
    if value is None:
        return None
    try:
        if key in _DECIMAL_FIELDS:
            return Decimal(str(value))
        if key in _DATE_FIELDS:
            return date.fromisoformat(str(value))
        if key in _INT_FIELDS:
            return int(value)
    except (InvalidOperation, ValueError):
        return None
    return value


def _item_out(it: ExtractionQueueItem) -> ExtractionItemOut:
    return ExtractionItemOut(
        id=str(it.id),
        contract_id=str(it.contract_id) if it.contract_id else None,
        status=it.status,
        extracted_fields=it.extracted_fields,
        extracted_clauses=it.extracted_clauses,
        field_confidence=it.field_confidence,
        injection_flags=it.injection_flags,
        source_document=it.source_document,
    )


@router.post(
    "/contracts/{contract_id}/extract",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RunResponse,
    dependencies=[Depends(require_permission("contract:write"))],
)
async def run_extraction(
    contract_id: str,
    body: dict,
    principal: Principal = Depends(get_current_principal),
) -> RunResponse:
    """Run the (untrusted-input sandbox) extraction agent for a contract document."""
    from app.agents.extraction import extraction_graph
    from app.core.agent_run import agent_run

    text_doc = body.get("contract_text", "")
    async with agent_run(
        tenant_id=principal.tenant_id, agent="contract_extraction", trigger="user_request"
    ) as run:
        out = await extraction_graph.ainvoke(
            {
                "tenant_id": principal.tenant_id,
                "contract_id": contract_id,
                "run_id": str(run.run_id),
                "contract_text": text_doc,
                "source_document": body.get("source_document", ""),
            }
        )
        run.set_outputs(
            {"queue_id": out.get("queue_id"), "injection_flags": out.get("injection_flags")}
        )
    return RunResponse(status="queued", detail={"queue_id": out.get("queue_id")})


@router.get(
    "/extraction/verification-queue",
    response_model=ExtractionListResponse,
    dependencies=[Depends(require_permission("contract:read"))],
)
async def verification_queue(
    status_filter: str = Query("needs_verification", alias="status"),
    session: AsyncSession = Depends(get_session),
) -> ExtractionListResponse:
    rows = (
        await session.scalars(
            select(ExtractionQueueItem)
            .where(ExtractionQueueItem.status == status_filter)
            .order_by(desc(ExtractionQueueItem.created_at))
        )
    ).all()
    return ExtractionListResponse(items=[_item_out(it) for it in rows])


@router.get(
    "/extraction/verification-queue/{item_id}",
    response_model=ExtractionItemOut,
    dependencies=[Depends(require_permission("contract:read"))],
)
async def verification_item(
    item_id: str, session: AsyncSession = Depends(get_session)
) -> ExtractionItemOut:
    it = await session.get(ExtractionQueueItem, UUID(item_id))
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "queue item not found")
    return _item_out(it)


@router.post(
    "/extraction/verification-queue/{item_id}/verify",
    dependencies=[Depends(require_permission("contract:write"))],
)
async def verify_item(
    item_id: str,
    body: VerifyRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Verification is gated to the configured roles (legal/admin).
    if principal.role not in settings.extraction_verify_roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "verify requires legal/admin role")
    it = await session.get(ExtractionQueueItem, UUID(item_id))
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "queue item not found")
    if it.status in ("verified", "rejected", "promoted"):
        raise HTTPException(status.HTTP_409_CONFLICT, "item already verified/rejected")

    if body.action == "reject":
        it.status = "rejected"
        it.verified_by = UUID(principal.user_id)
        it.verified_at = datetime.now(UTC)
        await session.commit()
        return {"id": item_id, "status": "rejected"}

    # promote → write verified fields to the canonical Contract.
    merged = {**it.extracted_fields, **(body.edited_fields or {})}
    if it.contract_id is not None:
        contract = await session.get(Contract, it.contract_id)
        if contract is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "linked contract not found")
        for key, raw in merged.items():
            if key in _PROMOTABLE:
                coerced = _coerce(key, raw)
                if coerced is not None:
                    setattr(contract, key, coerced)
    it.status = "promoted"
    it.verified_by = UUID(principal.user_id)
    it.verified_at = datetime.now(UTC)
    await record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        event_type="extraction.promoted",
        actor="human",
        actor_user_id=UUID(principal.user_id),
        payload={
            "queue_id": item_id,
            "contract_id": str(it.contract_id) if it.contract_id else None,
            "verified_by": principal.user_id,
            "edited_fields": body.edited_fields or {},
        },
        run_id=it.run_id,
    )
    await session.commit()
    return {"id": item_id, "status": "promoted", "promoted_fields": list(merged.keys())}
