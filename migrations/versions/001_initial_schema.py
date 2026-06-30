"""initial schema — tenants, entities, roles, users, agent_runs, audit_events

Phase 0 foundation: extensions, six core tables, RLS (ENABLE + FORCE, fail-closed
policies with WITH CHECK), append-only enforcement on the audit backbone
(agent_runs no-delete + terminal-state guard; audit_events no-update/no-delete),
and the 7 seeded system roles.

Revision ID: 001
Revises:
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Extensions ───────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")          # pgvector (Phase 4)
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')     # uuid_generate_v4()
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")         # trigram (Phase 2 matching)

    # ── tenants (isolation root; not RLS-scoped) ─────────────────────────
    op.execute(
        """
        CREATE TABLE tenants (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name               TEXT        NOT NULL,
            slug               TEXT        NOT NULL UNIQUE,
            auth0_org_id       TEXT        UNIQUE,
            encryption_key_ref TEXT        NOT NULL,
            plan               TEXT        NOT NULL DEFAULT 'standard',
            status             TEXT        NOT NULL DEFAULT 'active',
            autonomy_config    JSONB       NOT NULL DEFAULT '{}'::jsonb,
            data_residency     TEXT        NOT NULL DEFAULT 'us',
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT tenants_plan_chk   CHECK (plan IN ('standard','enterprise')),
            CONSTRAINT tenants_status_chk CHECK (status IN ('active','suspended')),
            CONSTRAINT tenants_slug_chk   CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$')
        )
        """
    )

    # ── entities (legal entity / business unit) ──────────────────────────
    op.execute(
        """
        CREATE TABLE entities (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id        UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name             TEXT        NOT NULL,
            type             TEXT        NOT NULL,
            external_ref     TEXT,
            parent_entity_id UUID        REFERENCES entities(id) ON DELETE SET NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT entities_type_chk CHECK (type IN ('legal_entity','business_unit')),
            CONSTRAINT entities_no_self_parent CHECK (parent_entity_id IS DISTINCT FROM id)
        )
        """
    )
    op.execute("CREATE INDEX ix_entities_tenant ON entities (tenant_id)")
    op.execute("CREATE INDEX ix_entities_parent ON entities (parent_entity_id)")
    op.execute("CREATE UNIQUE INDEX uq_entities_tenant_name ON entities (tenant_id, name)")

    # ── roles (global definitions) ───────────────────────────────────────
    op.execute(
        """
        CREATE TABLE roles (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name        TEXT        NOT NULL UNIQUE,
            description TEXT,
            permissions JSONB       NOT NULL DEFAULT '[]'::jsonb,
            is_system   BOOLEAN     NOT NULL DEFAULT true,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ── users (tenant-scoped) ────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE users (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            auth0_id      TEXT        NOT NULL UNIQUE,
            email         TEXT        NOT NULL,
            full_name     TEXT,
            role_id       UUID        REFERENCES roles(id) ON DELETE SET NULL,
            entity_id     UUID        REFERENCES entities(id) ON DELETE SET NULL,
            status        TEXT        NOT NULL DEFAULT 'active',
            last_login_at TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT users_status_chk CHECK (status IN ('active','disabled'))
        )
        """
    )
    op.execute("CREATE INDEX ix_users_tenant ON users (tenant_id)")
    op.execute("CREATE INDEX ix_users_entity ON users (entity_id)")
    op.execute("CREATE UNIQUE INDEX uq_users_tenant_email ON users (tenant_id, lower(email))")

    # ── agent_runs (immutable audit backbone) ────────────────────────────
    op.execute(
        """
        CREATE TABLE agent_runs (
            run_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            -- NO ACTION (not CASCADE): the immutable audit log must survive tenant
            -- deletion, and a DO INSTEAD NOTHING delete-rule (below) is incompatible
            -- with an RI cascade anyway. Tenant offboarding archives, never cascades.
            tenant_id      UUID        NOT NULL REFERENCES tenants(id),
            agent          TEXT        NOT NULL,
            trigger        TEXT        NOT NULL,
            status         TEXT        NOT NULL DEFAULT 'running',
            actor          TEXT        NOT NULL DEFAULT 'ai',
            actor_user_id  UUID        REFERENCES users(id),
            confidence     NUMERIC(4,3),
            inputs_ref     TEXT,
            outputs_ref    TEXT,
            parent_run_id  UUID        REFERENCES agent_runs(run_id),
            correlation_id TEXT,
            error_message  TEXT,
            started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at   TIMESTAMPTZ,
            CONSTRAINT agent_runs_status_chk CHECK (status IN ('running','completed','failed','cancelled')),
            CONSTRAINT agent_runs_actor_chk  CHECK (actor IN ('ai','human')),
            CONSTRAINT agent_runs_conf_chk   CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
        )
        """
    )
    op.execute("CREATE INDEX ix_agent_runs_tenant ON agent_runs (tenant_id)")
    op.execute("CREATE INDEX ix_agent_runs_agent ON agent_runs (tenant_id, agent)")
    op.execute("CREATE INDEX ix_agent_runs_started ON agent_runs (tenant_id, started_at DESC)")
    op.execute("CREATE INDEX ix_agent_runs_correlation ON agent_runs (correlation_id)")

    # ── audit_events (fully immutable) ───────────────────────────────────
    op.execute(
        """
        CREATE TABLE audit_events (
            event_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            run_id        UUID        REFERENCES agent_runs(run_id),
            -- NO ACTION (not CASCADE): immutable audit rows are never cascade-deleted.
            tenant_id     UUID        NOT NULL REFERENCES tenants(id),
            event_type    TEXT        NOT NULL,
            payload       JSONB       NOT NULL DEFAULT '{}'::jsonb,
            actor         TEXT        NOT NULL DEFAULT 'ai',
            actor_user_id UUID        REFERENCES users(id),
            request_id    TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT audit_events_actor_chk CHECK (actor IN ('ai','human','system'))
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_events_tenant ON audit_events (tenant_id, created_at DESC)")
    op.execute("CREATE INDEX ix_audit_events_run ON audit_events (run_id)")
    op.execute("CREATE INDEX ix_audit_events_type ON audit_events (tenant_id, event_type)")

    # ── Row-Level Security: ENABLE + FORCE on every tenant-scoped table ──
    for table in ("entities", "users", "agent_runs", "audit_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE  ROW LEVEL SECURITY")
        # NULLIF(..., '') treats BOTH an unset GUC (NULL) and an empty-string GUC
        # as "no tenant" → the cast yields NULL → `tenant_id = NULL` is falsy →
        # zero rows (fail-closed). Without NULLIF, an empty-string GUC would raise
        # "invalid input syntax for type uuid" instead of safely returning nothing.
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING      (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            """
        )

    # ── Append-only enforcement on the audit backbone ───────────────────
    op.execute("CREATE RULE agent_runs_no_delete   AS ON DELETE TO agent_runs   DO INSTEAD NOTHING")
    op.execute("CREATE RULE audit_events_no_update AS ON UPDATE TO audit_events DO INSTEAD NOTHING")
    op.execute("CREATE RULE audit_events_no_delete AS ON DELETE TO audit_events DO INSTEAD NOTHING")

    # Guard agent_runs UPDATE: terminal runs are frozen; immutable columns can't change.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION agent_runs_guard_update() RETURNS trigger AS $$
        BEGIN
            IF OLD.status IN ('completed','failed','cancelled') THEN
                RAISE EXCEPTION 'agent_run % is terminal and cannot be modified', OLD.run_id;
            END IF;
            IF NEW.run_id   <> OLD.run_id   OR NEW.tenant_id <> OLD.tenant_id
               OR NEW.agent <> OLD.agent    OR NEW.trigger   <> OLD.trigger
               OR NEW.started_at <> OLD.started_at THEN
                RAISE EXCEPTION 'immutable columns on agent_runs may not change';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_agent_runs_guard
            BEFORE UPDATE ON agent_runs
            FOR EACH ROW EXECUTE FUNCTION agent_runs_guard_update()
        """
    )

    # ── Seed the 7 system roles ──────────────────────────────────────────
    op.execute(
        """
        INSERT INTO roles (name, description, permissions, is_system) VALUES
         ('admin',           'Tenant administrator',  '["*"]', true),
         ('cfo',             'Finance leader',        '["dashboard:read","portfolio:read","opportunity:read","contract:read","spend:read","recovery:read","renewal:read","nirvana:use"]', true),
         ('cpo',             'Procurement leader',    '["dashboard:read","opportunity:read","opportunity:write","contract:read","vendor:read","renewal:read","renewal:write","spend:read","nirvana:use"]', true),
         ('category_mgr',    'Category/sourcing mgr', '["dashboard:read","spend:read","opportunity:read","vendor:read","nirvana:use"]', true),
         ('ap_analyst',      'AP/finance analyst',    '["dashboard:read","recovery:read","recovery:write","data_quality:read","data_quality:write","spend:read","nirvana:use"]', true),
         ('legal',           'Legal/contract owner',  '["dashboard:read","contract:read","contract:write","indexation:read","renewal:read","nirvana:use"]', true),
         ('portfolio_admin', 'Group portfolio admin', '["dashboard:read","portfolio:read","opportunity:read","contract:read","spend:read","vendor:read","renewal:read","recovery:read","nirvana:use"]', true)
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_agent_runs_guard ON agent_runs")
    op.execute("DROP FUNCTION IF EXISTS agent_runs_guard_update()")
    op.execute("DROP RULE IF EXISTS agent_runs_no_delete ON agent_runs")
    op.execute("DROP RULE IF EXISTS audit_events_no_update ON audit_events")
    op.execute("DROP RULE IF EXISTS audit_events_no_delete ON audit_events")
    op.execute("DROP TABLE IF EXISTS audit_events")
    op.execute("DROP TABLE IF EXISTS agent_runs")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS entities")
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("DROP TABLE IF EXISTS tenants")
