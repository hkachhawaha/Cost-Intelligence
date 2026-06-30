"""Celery tasks for matching. Triggered by `records.landed` (Phase 1) and the
manual rematch endpoint. Idempotent (UPSERT keyed on (tenant, spend))."""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select

from app.agents.matching import matching_graph
from app.core.database import session_for_tenant
from app.models.matching import MatchResult
from app.models.spend import SpendRecord
from app.workers import celery

BATCH_SIZE = 500


@celery.task(bind=True, max_retries=3, default_retry_delay=30, acks_late=True)
def run_matching(
    self, tenant_id: str, spend_ids: list[str], trigger: str = "records.landed"
) -> dict:
    return asyncio.run(run_matching_async(tenant_id, spend_ids, trigger))


async def run_matching_async(tenant_id: str, spend_ids: list[str], trigger: str) -> dict:
    final = await matching_graph.ainvoke(
        {"tenant_id": tenant_id, "spend_ids": spend_ids, "trigger": trigger}
    )
    return {"summary": final.get("summary", {}), "coverage_pct": final.get("coverage_pct", 0.0)}


@celery.task(acks_late=True)
def rematch_unmatched(tenant_id: str, scope: str = "unmatched") -> dict:
    return asyncio.run(_rematch_async(tenant_id, scope))


async def _rematch_async(tenant_id: str, scope: str) -> dict:
    """Select the spend ids in scope and re-run the matching agent over them."""
    async with await session_for_tenant(tenant_id) as session:
        if scope == "all":
            stmt = select(SpendRecord.id).where(SpendRecord.tenant_id == UUID(tenant_id))
        elif scope == "low_confidence":
            stmt = select(MatchResult.spend_id).where(MatchResult.confidence < 0.70)
        else:  # unmatched
            stmt = select(MatchResult.spend_id).where(MatchResult.method == "unmatched")
        spend_ids = [str(x) for x in (await session.execute(stmt)).scalars().all()]

    if not spend_ids:
        return {"summary": {}, "coverage_pct": 0.0, "spend_ids": 0}
    return await run_matching_async(tenant_id, spend_ids, trigger="rematch")
