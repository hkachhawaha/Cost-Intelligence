"""Phase 1 ingestion integration tests (live Postgres + Redis, migration 002 applied).

Uses a FakeConnector (no Google/OAuth/network) so the Ingestion agent graph runs
end-to-end deterministically. Covers the DoD: vendor collapse, quarantine + drift,
records.landed, immutable AgentRun, idempotency, and tenant isolation.

Run:
    RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_ingestion.py -v
"""

from __future__ import annotations

import json
import uuid

import pandas as pd
import pytest

from tests.conftest import requires_db

pytestmark = requires_db

CONTRACT_COLS = [
    "contract_number",
    "vendor_name",
    "acv",
    "tcv",
    "start_date",
    "end_date",
    "renewal_type",
    "renewal_notice_days",
]


def _contracts_df() -> pd.DataFrame:
    rows = [
        ["C-1", "Acme Inc", "120000", "360000", "2026-01-01", "2026-12-31", "auto", "90"],
        ["C-2", "ACME, LLC", "50000", "150000", "2026-01-01", "2026-12-31", "none", "0"],
        ["C-3", "Globex", "200000", "600000", "2026-01-01", "2026-12-31", "option", "30"],
        # bad: acv non-numeric → quarantined
        ["C-4", "BadCo", "abc", "100", "2026-01-01", "2026-12-31", "none", "0"],
    ]
    return pd.DataFrame(rows, columns=CONTRACT_COLS)


# ---- fake connector ------------------------------------------------------


def _make_fake_connector(tenant_id: str, source_id: str, frames: dict[str, pd.DataFrame]):
    from app.connectors.base import ConnectorBase, ConnectorConfig

    class FakeConnector(ConnectorBase):
        source_type = "fake"

        async def authenticate(self) -> None:
            return None

        async def fetch_raw(self, dataset: str) -> pd.DataFrame:
            return self.map_columns(frames.get(dataset, pd.DataFrame()).copy(), dataset)

    return FakeConnector(ConnectorConfig(column_mappings={}), tenant_id, source_id)


# ---- db helpers (admin = superuser, bypasses RLS for seeding/asserting) --


def _dsn() -> str:
    from app.core.config import settings

    return settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")


def _admin():
    import psycopg

    return psycopg.connect(_dsn(), autocommit=True)


def _count(cur, table: str, tenant_id: str) -> int:
    cur.execute(f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (tenant_id,))
    return cur.fetchone()[0]


@pytest.fixture()
def seeded():
    """Create a tenant + data_source; ensure a non-superuser role for RLS checks."""
    tenant_id, source_id = str(uuid.uuid4()), str(uuid.uuid4())
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (id, name, slug, encryption_key_ref) VALUES (%s,%s,%s,'kms://t')",
            (tenant_id, "Acme", f"acme{tenant_id[:8]}"),
        )
        cur.execute(
            "INSERT INTO data_sources (id, tenant_id, name, source_type, status) "
            "VALUES (%s,%s,'Sheet','google_sheets','connected')",
            (source_id, tenant_id),
        )
        cur.execute(
            """
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rls_app_user') THEN
                    CREATE ROLE rls_app_user LOGIN PASSWORD 'rls_test' NOSUPERUSER;
                END IF;
            END $$;
            """
        )
        cur.execute("GRANT USAGE ON SCHEMA public TO rls_app_user")
        cur.execute("GRANT SELECT ON contracts, vendors, spend_records, invoices TO rls_app_user")
    admin.close()
    yield tenant_id, source_id
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "TRUNCATE tenants, vendors, vendor_aliases, contracts, spend_records, invoices, "
            "data_sources, ingestion_batches, staged_records, agent_runs, audit_events CASCADE"
        )
    admin.close()


async def _ingest(tenant_id: str, source_id: str, dataset: str, df: pd.DataFrame) -> dict:
    """Create a batch row, then drive the ingestion graph with a fake connector."""
    from datetime import UTC, datetime

    from app.agents.ingestion import ingestion_graph
    from app.core.database import session_for_tenant
    from app.models.staging import IngestionBatch

    async with await session_for_tenant(tenant_id) as session:
        batch = IngestionBatch(
            tenant_id=uuid.UUID(tenant_id),
            source_id=uuid.UUID(source_id),
            dataset_type=dataset,
            status="running",
            started_at=datetime.now(UTC),
        )
        session.add(batch)
        await session.commit()
        batch_id = str(batch.id)

    connector = _make_fake_connector(tenant_id, source_id, {dataset: df})
    return await ingestion_graph.ainvoke(
        {
            "tenant_id": tenant_id,
            "source_id": source_id,
            "dataset_type": dataset,
            "batch_id": batch_id,
            "connector": connector,
        }
    )


def _stream_has(tenant_id: str, stream: str) -> bool:
    import redis

    from app.core.config import settings

    r = redis.from_url(str(settings.redis_url))
    for _id, fields in r.xrange(f"stream:{stream}") or []:
        raw = fields.get(b"data") if isinstance(fields, dict) else None
        if raw and json.loads(raw).get("tenant_id") == tenant_id:
            return True
    return False


# ---- tests ---------------------------------------------------------------


def test_migration_002_tables_present():
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name IN "
            "('data_sources','vendors','vendor_aliases','contracts','contract_line_items',"
            "'contract_clauses','spend_records','invoices','invoice_line_items',"
            "'ingestion_batches','staged_records')"
        )
        assert cur.fetchone()[0] == 11
    admin.close()


async def test_ingestion_collapse_quarantine_drift_audit(seeded):
    tenant_id, source_id = seeded
    final = await _ingest(tenant_id, source_id, "contracts", _contracts_df())

    assert final["inserted"] == 3  # three valid rows persisted
    admin = _admin()
    with admin.cursor() as cur:
        assert _count(cur, "contracts", tenant_id) == 3
        assert _count(cur, "vendors", tenant_id) == 2  # Acme variants collapse → 2
        assert _count(cur, "vendor_aliases", tenant_id) == 3  # three raw spellings recorded
        assert _count(cur, "staged_records", tenant_id) == 1  # the bad row quarantined
        # immutable AgentRun recorded (actor=ai, completed)
        cur.execute(
            "SELECT count(*) FROM agent_runs WHERE tenant_id=%s AND agent='ingestion' "
            "AND actor='ai' AND status='completed'",
            (tenant_id,),
        )
        assert cur.fetchone()[0] == 1
    admin.close()

    # DoD events on the streams
    assert _stream_has(tenant_id, "records.landed")
    assert _stream_has(tenant_id, "data_quality.schema_drift")


async def test_ingestion_idempotent(seeded):
    tenant_id, source_id = seeded
    first = await _ingest(tenant_id, source_id, "contracts", _contracts_df())
    assert first["inserted"] == 3 and first["updated"] == 0
    second = await _ingest(tenant_id, source_id, "contracts", _contracts_df())
    assert second["inserted"] == 0 and second["updated"] == 3  # UPSERT, no duplicates
    admin = _admin()
    with admin.cursor() as cur:
        assert _count(cur, "contracts", tenant_id) == 3
    admin.close()


def test_rls_isolation_ingestion(seeded):
    import asyncio

    import psycopg

    tenant_id, source_id = seeded
    asyncio.run(_ingest(tenant_id, source_id, "contracts", _contracts_df()))

    host = _dsn().split("://", 1)[1].split("@", 1)[1]
    conn = psycopg.connect(f"postgresql://rls_app_user:rls_test@{host}", autocommit=True)
    other_tenant = str(uuid.uuid4())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (tenant_id,))
            cur.execute("SELECT count(*) FROM contracts")
            assert cur.fetchone()[0] == 3  # own tenant sees its rows
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (other_tenant,))
            cur.execute("SELECT count(*) FROM contracts")
            assert cur.fetchone()[0] == 0  # another tenant sees nothing
    finally:
        conn.close()
