"""Ingest-once sync pipeline (§5.8).

`run_full_sync_async` orchestrates the stages in-process — each wrapped in the
AgentRun lifecycle for immutable audit — then builds memory + embeddings:

    ingestion → enrichment(passthrough) → matching → detection → build_memory → embed → finalize

The Celery `initial_sync` / `refresh_sync` tasks call it (durable retry at the task
level). Keeping orchestration in one async function keeps version consistency simple
and makes the pipeline directly testable without a Celery worker.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from app.core.agent_run import agent_run
from app.core.database import session_for_tenant
from app.core.kpi_cache import RedisKpiCache
from app.core.redis import get_redis
from app.services.embeddings import EmbeddingsService
from app.services.memory import MemoryService
from app.services.memory_kpis import KpiComputer
from app.workers import celery

logger = logging.getLogger("sync")


async def run_full_sync_async(
    tenant_id: str, source_id: str, sync_run_id: str | None = None, kind: str = "initial"
) -> dict:
    # 1. Ingestion (reads source once).
    async with agent_run(
        tenant_id=tenant_id, agent="ingestion", trigger=kind, inputs={"source_id": source_id}
    ) as run:
        from app.workers.ingestion_tasks import run_ingestion_async

        ing = await run_ingestion_async(tenant_id, source_id)
        run.set_outputs(ing)
        run.set_confidence(1.0)

    # 2. Enrichment — passthrough in v1 (Phase 7 swaps the body).
    async with agent_run(tenant_id=tenant_id, agent="enrichment", trigger=kind) as run:
        run.set_outputs({"passthrough": True})
        run.set_confidence(1.0)

    # 3. Matching — re-match all spend for the tenant.
    async with agent_run(tenant_id=tenant_id, agent="matching", trigger=kind) as run:
        from app.services.matching import MatchingService
        from app.services.matching_candidates import CandidateRetrievalService

        async with await session_for_tenant(tenant_id) as s:
            counts = await MatchingService(s, CandidateRetrievalService(s)).run_full_tenant_match(
                tenant_id
            )
            await s.commit()
        run.set_outputs(counts)

    # 4. Detection — run all rules.
    async with agent_run(tenant_id=tenant_id, agent="detection", trigger=kind) as run:
        from app.services.detection import DetectionService
        from app.services.scoring import ScoringService

        async with await session_for_tenant(tenant_id) as s:
            opps = await DetectionService(s, ScoringService()).run_all_rules(tenant_id)
            await s.commit()
        run.set_outputs({"opportunities": len(opps)})

    # 5. build_memory — KPIs in Python → Postgres snapshot → warm Redis.
    memory_version = 1
    async with agent_run(tenant_id=tenant_id, agent="memory_build", trigger=kind) as run:
        async with await session_for_tenant(tenant_id) as s:
            svc = MemoryService(s, RedisKpiCache(get_redis()), KpiComputer(s))
            snapshot = await svc.build(tenant_id, build_run_id=str(run.run_id))
            memory_version = snapshot.memory_version
            identified = str(snapshot.total_identified)
        run.set_outputs({"memory_version": memory_version, "total_identified": identified})
        run.set_confidence(1.0)

    # 6. embed_contracts — non-fatal (skips without GEMINI_API_KEY).
    embedded = 0
    async with agent_run(tenant_id=tenant_id, agent="embeddings", trigger=kind) as run:
        async with await session_for_tenant(tenant_id) as s:
            embedded = await EmbeddingsService(s).embed_tenant(
                tenant_id, memory_version=memory_version
            )
        run.set_outputs({"chunks": embedded})
        run.set_confidence(1.0)

    # 7. finalize — close sync_run + emit memory.rebuilt.
    if sync_run_id:
        from app.services.sync import SyncService

        async with await session_for_tenant(tenant_id) as s:
            await SyncService(s).complete(sync_run_id)
    await _emit_memory_rebuilt(tenant_id, kind, memory_version, embedded, identified)
    return {"memory_version": memory_version, "embedded_chunks": embedded, "kind": kind}


async def _emit_memory_rebuilt(tenant_id, kind, version, chunks, identified) -> None:
    client = get_redis()
    try:
        await client.xadd(
            "stream:memory.rebuilt",
            {
                "data": json.dumps(
                    {
                        "tenant_id": tenant_id,
                        "memory_version": version,
                        "kind": kind,
                        "embedded_chunks": chunks,
                        "total_identified": identified,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            },
        )
    finally:
        await client.aclose()


@celery.task(name="sync.initial_sync", acks_late=True)
def initial_sync(tenant_id: str, source_id: str, sync_run_id: str, kind: str = "initial") -> dict:
    return asyncio.run(run_full_sync_async(tenant_id, source_id, sync_run_id, kind))


@celery.task(name="sync.refresh_sync", acks_late=True)
def refresh_sync(tenant_id: str, source_id: str, sync_run_id: str) -> dict:
    return asyncio.run(run_full_sync_async(tenant_id, source_id, sync_run_id, kind="refresh"))
