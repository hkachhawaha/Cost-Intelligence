"""Celery task for detection. Triggered by `matches.completed`, a daily schedule,
or POST /detection/run."""

from __future__ import annotations

import asyncio

from app.agents.detection import detection_graph
from app.workers import celery


@celery.task(bind=True, max_retries=3, default_retry_delay=30, acks_late=True)
def run_detection(self, tenant_id: str, trigger: str = "matches.completed") -> dict:
    return asyncio.run(run_detection_async(tenant_id, trigger))


async def run_detection_async(tenant_id: str, trigger: str = "matches.completed") -> dict:
    final = await detection_graph.ainvoke({"tenant_id": tenant_id, "trigger": trigger})
    return {
        "totals": final.get("totals", {}),
        "by_type": final.get("by_type", {}),
        "opportunity_count": final.get("opportunity_count", 0),
    }
