"""Idempotent canonical persistence.

UPSERT on `(tenant_id, source_id, source_row_hash)` so re-ingesting the same
sheet updates rather than duplicates. Unknown/unmapped fields are folded into
the table's `extra` JSONB so nothing is lost and no insert fails on a stray column.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import Table, func, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.spend import SpendRecord

_MODEL_BY_DATASET = {
    "contracts": Contract,
    "spend_records": SpendRecord,
    "invoices": Invoice,
}

# Inbound-only helper fields that are never table columns.
_DROP_FIELDS = {"vendor_name", "entity_name"}


def _shape_row(row: dict, columns: set[str]) -> dict:
    """Keep recognized columns; fold everything else into `extra` (lineage-preserving)."""
    shaped: dict = {}
    extra: dict = dict(row.get("extra") or {})
    for key, value in row.items():
        if key in _DROP_FIELDS or key == "extra":
            continue
        if key in columns:
            shaped[key] = value
        else:
            extra[key] = value
    if "extra" in columns:
        shaped["extra"] = extra
    return shaped


async def upsert_records(
    session: AsyncSession,
    *,
    tenant_id: str,
    source_id: str,
    batch_id: str,
    dataset: str,
    rows: list[dict],
) -> tuple[int, int]:
    """Returns (inserted, updated). Idempotent via ON CONFLICT DO UPDATE."""
    if not rows:
        return (0, 0)
    model = _MODEL_BY_DATASET[dataset]
    table = cast(Table, model.__table__)
    columns = {c.name for c in table.columns}

    shaped: list[dict] = []
    for r in rows:
        row = _shape_row(r, columns)
        row["tenant_id"] = UUID(tenant_id)
        row["source_id"] = UUID(source_id)
        row["ingestion_batch_id"] = UUID(batch_id)
        shaped.append(row)

    base_stmt = pg_insert(table).values(shaped)
    update_cols: dict[str, Any] = {
        c.name: base_stmt.excluded[c.name]
        for c in table.columns
        if c.name not in ("id", "tenant_id", "source_id", "source_row_hash", "created_at")
        and c.name in shaped[0]
    }
    if "updated_at" in columns:
        update_cols["updated_at"] = func.now()  # bump on conflict-update

    # `xmax = 0` is true only for rows freshly INSERTed in this upsert; non-zero
    # means the row already existed and was UPDATEd. The reliable insert/update split.
    stmt = base_stmt.on_conflict_do_update(
        index_elements=["tenant_id", "source_id", "source_row_hash"],
        set_=update_cols,
    ).returning(table.c.id, literal_column("(xmax = 0)").label("is_new"))

    result = (await session.execute(stmt)).all()
    inserted = sum(1 for _id, is_new in result if is_new)
    updated = len(result) - inserted
    return (inserted, updated)
