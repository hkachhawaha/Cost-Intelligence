"""Integration tests against a live Postgres with migration 001 applied.

These are the load-bearing Phase 0 Definition-of-Done checks: provable tenant
isolation (RLS), fail-closed default, RLS write-check, and audit immutability.

RLS is BYPASSED for superusers, so the app must connect as a NON-superuser role.
Each test seeds as the admin (superuser → RLS bypassed) and verifies isolation
through a dedicated non-superuser role.

Run:
    docker compose -f infra/docker-compose.yml up -d postgres
    uv run alembic upgrade head
    RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration -v
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_db

pytestmark = requires_db


def _dsn() -> str:
    from app.core.config import settings

    return settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")


def _admin_conn():
    import psycopg

    return psycopg.connect(_dsn(), autocommit=True)


def _app_conn():
    """Connect as the non-superuser app role so RLS is enforced."""
    import psycopg

    host_part = _dsn().split("://", 1)[1].split("@", 1)[1]
    return psycopg.connect(f"postgresql://rls_app_user:rls_test@{host_part}", autocommit=True)


@pytest.fixture()
def seeded():
    """Seed two tenants + one entity each; ensure the non-superuser app role exists."""
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    admin = _admin_conn()
    with admin.cursor() as cur:
        for tid, slug in ((tenant_a, f"a{tenant_a.hex[:10]}"), (tenant_b, f"b{tenant_b.hex[:10]}")):
            cur.execute(
                "INSERT INTO tenants (id, name, slug, encryption_key_ref) VALUES (%s,%s,%s,%s)",
                (tid, f"Tenant {slug}", slug, "kms://test"),
            )
            cur.execute(
                "INSERT INTO entities (tenant_id, name, type) VALUES (%s,%s,'legal_entity')",
                (tid, f"Entity {slug}"),
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
        cur.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON entities, users, agent_runs, audit_events "
            "TO rls_app_user"
        )
    admin.close()
    yield tenant_a, tenant_b
    # Cleanup: TRUNCATE (not DELETE) — the audit tables' append-only delete-rules
    # would otherwise no-op the cleanup. TRUNCATE is not intercepted by ON DELETE
    # rules and CASCADE clears all tenant-scoped rows in one shot.
    admin = _admin_conn()
    with admin.cursor() as cur:
        cur.execute("TRUNCATE tenants, entities, users, agent_runs, audit_events CASCADE")
    admin.close()


def test_schema_present():
    """Migration applied: 6 tables exist and the 7 system roles are seeded."""
    admin = _admin_conn()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name IN ('tenants','entities','roles','users','agent_runs','audit_events')"
        )
        assert cur.fetchone()[0] == 6
        cur.execute("SELECT count(*) FROM roles WHERE is_system")
        assert cur.fetchone()[0] == 7
    admin.close()


def test_rls_tenant_isolation(seeded):
    tenant_a, tenant_b = seeded
    conn = _app_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_tenant', %s, false)", (str(tenant_a),))
        cur.execute("SELECT tenant_id FROM entities")
        rows = [str(r[0]) for r in cur.fetchall()]
        assert rows and all(r == str(tenant_a) for r in rows)
        assert str(tenant_b) not in rows
    conn.close()


def test_rls_fail_closed(seeded):
    conn = _app_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_tenant', '', false)")
        cur.execute("SELECT count(*) FROM entities")
        assert cur.fetchone()[0] == 0
    conn.close()


def test_rls_write_check_blocks_other_tenant(seeded):
    import psycopg

    tenant_a, tenant_b = seeded
    conn = _app_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_tenant', %s, false)", (str(tenant_a),))
        with pytest.raises(psycopg.errors.Error):
            cur.execute(
                "INSERT INTO entities (tenant_id, name, type) VALUES (%s,'x','legal_entity')",
                (tenant_b,),
            )
    conn.close()


def test_audit_event_immutable(seeded):
    tenant_a, _ = seeded
    admin = _admin_conn()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_events (tenant_id, event_type) VALUES (%s,'t') RETURNING event_id",
            (tenant_a,),
        )
        event_id = cur.fetchone()[0]
        cur.execute("DELETE FROM audit_events WHERE event_id=%s", (event_id,))  # no-op rule
        cur.execute(
            "UPDATE audit_events SET event_type='x' WHERE event_id=%s", (event_id,)
        )  # no-op
        cur.execute("SELECT event_type FROM audit_events WHERE event_id=%s", (event_id,))
        row = cur.fetchone()
        assert row is not None and row[0] == "t"  # survived delete, unchanged by update
        cur.execute("DELETE FROM audit_events WHERE event_id=%s", (event_id,))
    admin.close()


def test_agent_run_no_delete_and_terminal_guard(seeded):
    import psycopg

    tenant_a, _ = seeded
    admin = _admin_conn()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_runs (tenant_id, agent, trigger) VALUES (%s,'ingestion','event') "
            "RETURNING run_id",
            (tenant_a,),
        )
        run_id = cur.fetchone()[0]
        # DELETE is a no-op (rule).
        cur.execute("DELETE FROM agent_runs WHERE run_id=%s", (run_id,))
        cur.execute("SELECT count(*) FROM agent_runs WHERE run_id=%s", (run_id,))
        assert cur.fetchone()[0] == 1
        # running → completed is allowed once.
        cur.execute("UPDATE agent_runs SET status='completed' WHERE run_id=%s", (run_id,))
        # Re-opening / modifying a terminal run raises (trigger).
        with pytest.raises(psycopg.errors.Error):
            cur.execute("UPDATE agent_runs SET status='running' WHERE run_id=%s", (run_id,))
    admin.close()
