"""Append-only audit writers.

The API every agent (and human-action path) calls to record an immutable
`AgentRun` and fine-grained `AuditEvent` rows. Immutability is enforced in the
database (Migration 001 rules + trigger); these helpers are the write side.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.audit_event import AuditEvent


async def record_agent_run(
    session: AsyncSession,
    *,
    tenant_id: str,
    agent: str,
    trigger: str,
    actor: str = "ai",
    actor_user_id: UUID | None = None,
    correlation_id: str | None = None,
    parent_run_id: UUID | None = None,
) -> AgentRun:
    run = AgentRun(
        tenant_id=UUID(tenant_id),
        agent=agent,
        trigger=trigger,
        status="running",
        actor=actor,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        parent_run_id=parent_run_id,
    )
    session.add(run)
    await session.flush()
    return run


async def complete_agent_run(
    session: AsyncSession,
    run: AgentRun,
    *,
    status: str = "completed",
    confidence: float | None = None,
    inputs_ref: str | None = None,
    outputs_ref: str | None = None,
    error_message: str | None = None,
) -> None:
    run.status = status
    # Confidence is stored as NUMERIC; convert via str() to avoid float binary drift.
    run.confidence = Decimal(str(confidence)) if confidence is not None else None
    run.inputs_ref = inputs_ref
    run.outputs_ref = outputs_ref
    run.error_message = error_message
    run.completed_at = datetime.now(UTC)
    await session.flush()


async def record_audit_event(
    session: AsyncSession,
    *,
    tenant_id: str,
    event_type: str,
    payload: dict,
    actor: str = "system",
    actor_user_id: UUID | None = None,
    run_id: UUID | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    evt = AuditEvent(
        tenant_id=UUID(tenant_id),
        event_type=event_type,
        payload=payload,
        actor=actor,
        actor_user_id=actor_user_id,
        run_id=run_id,
        request_id=request_id,
    )
    session.add(evt)
    await session.flush()
    return evt
