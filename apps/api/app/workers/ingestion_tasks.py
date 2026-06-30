"""Celery tasks driving the Ingestion agent. Idempotent (UPSERT keyed on hash)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from app.agents.ingestion import ingestion_graph
from app.connectors.registry import build_connector
from app.core.database import session_for_tenant
from app.workers import celery

DATASETS = ("contracts", "spend_records", "invoices")


@celery.task(bind=True, max_retries=3, default_retry_delay=30, acks_late=True)
def run_ingestion(self, tenant_id: str, source_id: str) -> dict:
    """Drive the connector + Ingestion agent across all three datasets."""
    return asyncio.run(run_ingestion_async(tenant_id, source_id))


async def run_ingestion_async(tenant_id: str, source_id: str) -> dict:
    connector = await build_connector(tenant_id, source_id)
    results: dict[str, dict] = {}
    for dataset in DATASETS:
        async with await session_for_tenant(tenant_id) as session:
            from app.models.staging import IngestionBatch

            batch = IngestionBatch(
                tenant_id=UUID(tenant_id),
                source_id=UUID(source_id),
                dataset_type=dataset,
                status="running",
                started_at=datetime.now(UTC),
            )
            session.add(batch)
            await session.commit()
            batch_id = str(batch.id)

        final = await ingestion_graph.ainvoke(
            {
                "tenant_id": tenant_id,
                "source_id": source_id,
                "dataset_type": dataset,
                "batch_id": batch_id,
                "connector": connector,
            }
        )
        results[dataset] = {
            "inserted": final.get("inserted", 0),
            "updated": final.get("updated", 0),
            "valid": final["validation"].is_valid,
        }
        await _finalize_batch(tenant_id, batch_id, final)

    await _stamp_source_synced(tenant_id, source_id)
    return results


async def _finalize_batch(tenant_id: str, batch_id: str, final: dict) -> None:
    from app.models.staging import IngestionBatch

    async with await session_for_tenant(tenant_id) as session:
        batch = await session.get(IngestionBatch, UUID(batch_id))
        if batch is None:
            return
        inserted = final.get("inserted", 0)
        updated = final.get("updated", 0)
        quarantined = len(final["validation"].quarantined_rows) if final.get("validation") else 0
        batch.inserted_count = inserted
        batch.updated_count = updated
        batch.record_count = inserted + updated
        batch.error_count = quarantined
        batch.status = "completed" if not final.get("error") else "failed"
        batch.completed_at = datetime.now(UTC)
        await session.commit()


async def _stamp_source_synced(tenant_id: str, source_id: str) -> None:
    from app.models.staging import DataSource

    async with await session_for_tenant(tenant_id) as session:
        ds = await session.get(DataSource, UUID(source_id))
        if ds is not None:
            ds.last_synced_at = datetime.now(UTC)
            ds.status = "connected"
            ds.last_error = None
            await session.commit()


@celery.task(acks_late=True)
def refresh_source(tenant_id: str, source_id: str) -> dict:
    """User-initiated Refresh (§5.8). Re-reads + re-ingests; Phase 4 wraps in full sync."""
    return run_ingestion(tenant_id, source_id)


@celery.task(acks_late=True)
def process_quarantine_review(
    tenant_id: str, staged_id: str, action: str, patch: dict | None = None
) -> dict:
    return asyncio.run(process_quarantine_async(tenant_id, staged_id, action, patch))


async def process_quarantine_async(tenant_id, staged_id, action, patch):
    from app.models.staging import StagedRecord
    from app.schemas.data_contracts import DATASET_CONTRACTS
    from app.services.ingestion_persistence import upsert_records

    async with await session_for_tenant(tenant_id) as session:
        rec = await session.get(StagedRecord, UUID(staged_id))
        if rec is None:
            return {"status": "not_found"}

        if action == "discard":
            rec.status = "discarded"
        elif action in ("promote", "fix"):
            data = {**rec.raw_data, **(patch or {})}
            data.pop("source_row_hash", None)
            dataset = {"contract": "contracts", "spend": "spend_records", "invoice": "invoices"}[
                rec.record_type
            ]
            schema = DATASET_CONTRACTS[dataset]
            model = schema(**data)  # raises if still invalid
            row = model.model_dump()
            row["source_row_hash"] = rec.source_row_hash
            row["source_system"] = "sheets"
            # vendor normalization for the promoted row
            from app.services.vendor_normalization import VendorNormalizationService

            svc = VendorNormalizationService(session, tenant_id)
            vendor = await svc.get_or_create_canonical(row["vendor_name"], source=dataset)
            row["vendor_id"] = str(vendor.id)
            row["vendor_name_raw"] = row.pop("vendor_name")
            await upsert_records(
                session,
                tenant_id=tenant_id,
                source_id=str(rec.source_id),
                batch_id=str(rec.batch_id),
                dataset=dataset,
                rows=[row],
            )
            rec.status = "promoted" if action == "promote" else "fixed"
        rec.resolved_at = datetime.now(UTC)
        await session.commit()
        return {"status": rec.status}
