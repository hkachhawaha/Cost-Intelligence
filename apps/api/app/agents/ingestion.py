"""Ingestion agent (LangGraph) — deterministic, L2 autonomy, no LLM.

Drives a connector across one dataset: fetch → hash → validate → (quarantine
bad rows) → normalize vendors → dedupe → UPSERT → emit events → audit. Valid
rows are never lost to bad neighbors; violations are quarantined and a
`data_quality.schema_drift` event is raised.
"""

from __future__ import annotations

from typing import TypedDict
from uuid import UUID, uuid4

import pandas as pd
from langgraph.graph import END, StateGraph

from app.connectors.base import ConnectorBase
from app.core.audit import complete_agent_run, record_agent_run, record_audit_event
from app.core.database import session_for_tenant
from app.schemas.data_contracts import DATASET_CONTRACTS, ValidationResult
from app.services.events import publish_event
from app.services.ingestion_persistence import upsert_records
from app.services.vendor_normalization import VendorNormalizationService

# Natural keys for the idempotency hash, per dataset.
NATURAL_KEYS = {
    "contracts": ("contract_number", "vendor_name"),
    "spend_records": ("po_number", "vendor_name", "amount", "spend_date"),
    "invoices": ("invoice_number", "vendor_name"),
}


class IngestionState(TypedDict, total=False):
    tenant_id: str
    source_id: str
    dataset_type: str
    batch_id: str
    run_id: str
    connector: ConnectorBase
    raw_df: pd.DataFrame
    validation: ValidationResult
    normalized: list[dict]
    inserted: int
    updated: int
    error: str | None


async def start_run(s: IngestionState) -> IngestionState:
    async with await session_for_tenant(s["tenant_id"]) as session:
        run = await record_agent_run(
            session,
            tenant_id=s["tenant_id"],
            agent="ingestion",
            trigger="initial_sync",
            correlation_id=s.get("batch_id"),
        )
        await session.commit()
        return {**s, "run_id": str(run.run_id)}


async def fetch_raw(s: IngestionState) -> IngestionState:
    connector = s["connector"]
    await connector.authenticate()
    df = await connector.fetch_raw(s["dataset_type"])
    return {**s, "raw_df": df}


async def map_and_hash(s: IngestionState) -> IngestionState:
    df = s["raw_df"]
    connector = s["connector"]
    nk = NATURAL_KEYS[s["dataset_type"]]
    if not df.empty:
        df = df.copy()
        df["source_row_hash"] = df.apply(lambda r: connector.row_hash(r.to_dict(), nk), axis=1)
    return {**s, "raw_df": df}


async def validate(s: IngestionState) -> IngestionState:
    schema = DATASET_CONTRACTS[s["dataset_type"]]
    result = await s["connector"].validate(s["raw_df"], schema)
    return {**s, "validation": result}


async def normalize_vendors(s: IngestionState) -> IngestionState:
    rows = s["validation"].valid_rows
    async with await session_for_tenant(s["tenant_id"]) as session:
        svc = VendorNormalizationService(session, s["tenant_id"])
        for row in rows:
            vendor = await svc.get_or_create_canonical(row["vendor_name"], source=s["dataset_type"])
            row["vendor_id"] = str(vendor.id)
            row["vendor_name_raw"] = row.pop("vendor_name")
        await session.commit()
    return {**s, "normalized": rows}


async def deduplicate(s: IngestionState) -> IngestionState:
    """Collapse in-batch duplicates by source_row_hash (last wins);
    cross-batch dedup is the UPSERT's job."""
    seen: dict[str, dict] = {}
    for row in s["normalized"]:
        seen[row["source_row_hash"]] = row
    return {**s, "normalized": list(seen.values())}


async def persist_canonical(s: IngestionState) -> IngestionState:
    rows = []
    for r in s["normalized"]:
        r.setdefault("source_system", "sheets")
        rows.append(r)
    async with await session_for_tenant(s["tenant_id"]) as session:
        inserted, updated = await upsert_records(
            session,
            tenant_id=s["tenant_id"],
            source_id=s["source_id"],
            batch_id=s["batch_id"],
            dataset=s["dataset_type"],
            rows=rows,
        )
        await session.commit()
    return {**s, "inserted": inserted, "updated": updated}


async def quarantine(s: IngestionState) -> IngestionState:
    from app.models.staging import StagedRecord

    rt = {"contracts": "contract", "spend_records": "spend", "invoices": "invoice"}[
        s["dataset_type"]
    ]
    async with await session_for_tenant(s["tenant_id"]) as session:
        for i, raw in enumerate(s["validation"].quarantined_rows):
            errs = [v.model_dump() for v in s["validation"].violations if v.row_index == i]
            session.add(
                StagedRecord(
                    tenant_id=UUID(s["tenant_id"]),
                    source_id=UUID(s["source_id"]),
                    batch_id=UUID(s["batch_id"]),
                    record_type=rt,
                    raw_data=raw,
                    validation_errors=errs,
                    source_row_hash=str(raw.get("source_row_hash") or uuid4()),
                )
            )
        await session.commit()
    return s


async def emit_landed(s: IngestionState) -> IngestionState:
    await publish_event(
        "records.landed",
        {
            "tenant_id": s["tenant_id"],
            "source_id": s["source_id"],
            "batch_id": s["batch_id"],
            "dataset_type": s["dataset_type"],
            "record_count": s.get("inserted", 0) + s.get("updated", 0),
            "inserted": s.get("inserted", 0),
            "updated": s.get("updated", 0),
        },
    )
    # Partial batch: valid rows landed AND some rows failed → also raise drift.
    if s.get("validation") and s["validation"].violations:
        await _publish_drift(s)
    return s


async def emit_schema_drift(s: IngestionState) -> IngestionState:
    await _publish_drift(s)
    return s


async def _publish_drift(s: IngestionState) -> None:
    fields = sorted({v.field for v in s["validation"].violations})
    await publish_event(
        "data_quality.schema_drift",
        {
            "tenant_id": s["tenant_id"],
            "source_id": s["source_id"],
            "batch_id": s["batch_id"],
            "dataset_type": s["dataset_type"],
            "violation_count": len(s["validation"].violations),
            "affected_fields": fields,
            "sample_violations": [v.model_dump() for v in s["validation"].violations[:10]],
        },
    )


async def complete_run(s: IngestionState) -> IngestionState:
    from app.models.agent_run import AgentRun

    async with await session_for_tenant(s["tenant_id"]) as session:
        run = await session.get(AgentRun, UUID(s["run_id"]))
        assert run is not None  # just created in start_run
        status = "completed" if not s.get("error") else "failed"
        await complete_agent_run(session, run, status=status, error_message=s.get("error"))
        await record_audit_event(
            session,
            tenant_id=s["tenant_id"],
            event_type="records_landed",
            payload={
                "dataset": s["dataset_type"],
                "inserted": s.get("inserted", 0),
                "updated": s.get("updated", 0),
                "quarantined": len(s["validation"].quarantined_rows) if s.get("validation") else 0,
            },
            actor="ai",
            run_id=run.run_id,
        )
        await session.commit()
    return s


def route_on_validation(s: IngestionState) -> str:
    return "valid" if s["validation"].is_valid else "invalid"


def route_after_quarantine(s: IngestionState) -> str:
    return "persist_valid" if s["validation"].valid_rows else "drift_only"


def build_ingestion_graph():
    g = StateGraph(IngestionState)
    for node in (
        start_run,
        fetch_raw,
        map_and_hash,
        validate,
        normalize_vendors,
        deduplicate,
        persist_canonical,
        quarantine,
        emit_landed,
        emit_schema_drift,
        complete_run,
    ):
        g.add_node(node.__name__, node)

    g.set_entry_point("start_run")
    g.add_edge("start_run", "fetch_raw")
    g.add_edge("fetch_raw", "map_and_hash")
    g.add_edge("map_and_hash", "validate")
    g.add_conditional_edges(
        "validate",
        route_on_validation,
        {"valid": "normalize_vendors", "invalid": "quarantine"},
    )
    g.add_conditional_edges(
        "quarantine",
        route_after_quarantine,
        {"persist_valid": "normalize_vendors", "drift_only": "emit_schema_drift"},
    )
    g.add_edge("normalize_vendors", "deduplicate")
    g.add_edge("deduplicate", "persist_canonical")
    g.add_edge("persist_canonical", "emit_landed")
    g.add_edge("emit_landed", "complete_run")
    g.add_edge("emit_schema_drift", "complete_run")
    g.add_edge("complete_run", END)
    return g.compile()


ingestion_graph = build_ingestion_graph()
