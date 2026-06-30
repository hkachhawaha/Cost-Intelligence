"""AgentRunContext — the lifecycle wrapper that retrofits ALL agents (§5.4).

Wraps any agent/task so an `AgentRun` row transitions `running → completed | failed`,
with inputs/outputs snapshotted to S3 (best-effort) and confidence + actor recorded.
Provided as both an async context manager (`agent_run`) and a decorator (`audited_agent`).

The `running → terminal` UPDATE is permitted by Migration 001's guard trigger;
DELETE is blocked; `audit_events` is fully append-only.
"""

from __future__ import annotations

import functools
import logging
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text, update

from app.core.database import SessionFactory
from app.core.snapshots import S3SnapshotStore
from app.models.agent_run import AgentRun

logger = logging.getLogger("agent_run")


class RunHandle:
    """Mutable handle the wrapped agent uses to record confidence / outputs / actor."""

    def __init__(self, run_id: UUID, tenant_id: str, agent: str, trigger: str):
        self.run_id = run_id
        self.tenant_id = tenant_id
        self.agent = agent
        self.trigger = trigger
        self.confidence: Decimal | None = None
        self.outputs: Any = None
        self.actor: str = "ai"

    def set_confidence(self, value: Decimal | float | None) -> None:
        self.confidence = Decimal(str(value)) if value is not None else None

    def set_outputs(self, outputs: Any) -> None:
        self.outputs = outputs


async def _set_rls(session, tenant_id: str) -> None:
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id}
    )


@asynccontextmanager
async def agent_run(
    *, tenant_id: str, agent: str, trigger: str, inputs: Any | None = None, actor: str = "ai"
) -> AsyncIterator[RunHandle]:
    run_id = uuid4()
    snapshots = S3SnapshotStore()
    inputs_ref = (
        await snapshots.write(tenant_id, str(run_id), "inputs", inputs)
        if inputs is not None
        else None
    )

    async with SessionFactory() as session:
        await _set_rls(session, tenant_id)
        session.add(
            AgentRun(
                run_id=run_id,
                tenant_id=UUID(tenant_id),
                agent=agent,
                trigger=trigger,
                status="running",
                actor=actor,
                inputs_ref=inputs_ref,
                started_at=datetime.now(UTC),
            )
        )
        await session.commit()

    handle = RunHandle(run_id, tenant_id, agent, trigger)
    handle.actor = actor
    logger.info("agent_run start id=%s agent=%s tenant=%s", run_id, agent, tenant_id)

    try:
        yield handle
    except Exception as exc:
        outputs_ref = await snapshots.write(
            tenant_id, str(run_id), "error", {"error": str(exc), "trace": traceback.format_exc()}
        )
        await _finalize(
            tenant_id,
            run_id,
            status="failed",
            confidence=handle.confidence,
            outputs_ref=outputs_ref,
            error_message=str(exc)[:2000],
        )
        logger.error("agent_run failed id=%s agent=%s err=%s", run_id, agent, exc)
        raise
    else:
        outputs_ref = (
            await snapshots.write(tenant_id, str(run_id), "outputs", handle.outputs)
            if handle.outputs is not None
            else None
        )
        await _finalize(
            tenant_id,
            run_id,
            status="completed",
            confidence=handle.confidence,
            outputs_ref=outputs_ref,
            error_message=None,
        )
        logger.info("agent_run done id=%s agent=%s confidence=%s", run_id, agent, handle.confidence)


async def _finalize(tenant_id, run_id, *, status, confidence, outputs_ref, error_message) -> None:
    async with SessionFactory() as session:
        await _set_rls(session, tenant_id)
        await session.execute(
            update(AgentRun)
            .where(AgentRun.run_id == run_id)
            .values(
                status=status,
                confidence=confidence,
                outputs_ref=outputs_ref,
                error_message=error_message,
                completed_at=datetime.now(UTC),
            )
        )
        await session.commit()


def audited_agent(agent: str):
    """Decorator form. The wrapped coroutine receives a `run` kwarg (RunHandle)."""

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(
            *args,
            tenant_id: str,
            trigger: str = "event",
            inputs: Any | None = None,
            actor: str = "ai",
            **kwargs,
        ):
            async with agent_run(
                tenant_id=tenant_id, agent=agent, trigger=trigger, inputs=inputs, actor=actor
            ) as run:
                result = await fn(*args, tenant_id=tenant_id, trigger=trigger, run=run, **kwargs)
                if run.outputs is None:
                    run.set_outputs(
                        result if isinstance(result, dict | list) else {"result": str(result)}
                    )
                return result

        return wrapper

    return decorator
