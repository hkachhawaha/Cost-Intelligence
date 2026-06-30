"""Agentic automation & connectors — tasks, approval gates, reminders, connector creds,
learning labels, model calibration (Phase 9)

Depends on 008. Fail-closed RLS (NULLIF) + FORCE on all six tables; approval_gates is
no-delete and learning_labels is no-update/no-delete (immutable audit surfaces).

Revision ID: 009
Revises: 008
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "tasks", "approval_gates", "task_reminders",
    "connector_credentials", "learning_labels", "model_calibration",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE tasks (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id         UUID NOT NULL REFERENCES tenants(id),
            opportunity_id    UUID REFERENCES opportunities(id),
            title             TEXT NOT NULL,
            description       TEXT,
            type              TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'open',
            priority          TEXT NOT NULL DEFAULT 'normal',
            owner_id          UUID REFERENCES users(id),
            created_by        TEXT NOT NULL DEFAULT 'ai',
            due_date          DATE,
            reminder_at       TIMESTAMPTZ,
            reminder_sent     BOOLEAN NOT NULL DEFAULT FALSE,
            draft_document_id UUID REFERENCES document_drafts(id),
            workflow_run_id   UUID REFERENCES agent_runs(run_id),
            langgraph_thread_id TEXT,
            metadata          JSONB NOT NULL DEFAULT '{}',
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_tasks_tenant_status ON tasks (tenant_id, status)")
    op.execute("CREATE INDEX ix_tasks_owner ON tasks (tenant_id, owner_id)")
    op.execute("CREATE INDEX ix_tasks_reminder ON tasks (reminder_at) WHERE reminder_sent = FALSE")

    op.execute(
        """
        CREATE TABLE approval_gates (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            task_id         UUID NOT NULL REFERENCES tasks(id),
            workflow_run_id UUID REFERENCES agent_runs(run_id),
            action_type     TEXT NOT NULL,
            action_payload  JSONB NOT NULL,
            decision        TEXT NOT NULL DEFAULT 'pending',
            decided_by      UUID REFERENCES users(id),
            decided_at      TIMESTAMPTZ,
            decision_note   TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_approval_task ON approval_gates (tenant_id, task_id)")

    op.execute(
        """
        CREATE TABLE task_reminders (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            task_id     UUID NOT NULL REFERENCES tasks(id),
            fire_at     TIMESTAMPTZ NOT NULL,
            channel     TEXT NOT NULL DEFAULT 'email',
            sent        BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE connector_credentials (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id),
            source_id        UUID NOT NULL REFERENCES data_sources(id),
            connector_type   TEXT NOT NULL,
            auth_type        TEXT NOT NULL,
            secret_ref       TEXT NOT NULL,
            oauth_state      TEXT,
            token_expires_at TIMESTAMPTZ,
            scopes           JSONB NOT NULL DEFAULT '[]',
            status           TEXT NOT NULL DEFAULT 'pending',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE learning_labels (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            signal_type  TEXT NOT NULL,
            subject_id   UUID NOT NULL,
            features     JSONB NOT NULL,
            label        JSONB NOT NULL,
            actor_id     UUID REFERENCES users(id),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_learning_signal ON learning_labels (tenant_id, signal_type, created_at)")

    op.execute(
        """
        CREATE TABLE model_calibration (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id),
            model_kind    TEXT NOT NULL,
            version       INT NOT NULL,
            params        JSONB NOT NULL,
            metrics       JSONB NOT NULL DEFAULT '{}',
            active        BOOLEAN NOT NULL DEFAULT FALSE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_calibration UNIQUE (tenant_id, model_kind, version)
        )
        """
    )

    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE  ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {t}
                USING      (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            """
        )

    # Immutable audit surfaces.
    op.execute("CREATE RULE approval_gates_no_delete  AS ON DELETE TO approval_gates  DO INSTEAD NOTHING")
    op.execute("CREATE RULE learning_labels_no_update AS ON UPDATE TO learning_labels DO INSTEAD NOTHING")
    op.execute("CREATE RULE learning_labels_no_delete AS ON DELETE TO learning_labels DO INSTEAD NOTHING")


def downgrade() -> None:
    op.execute("DROP RULE IF EXISTS learning_labels_no_delete ON learning_labels")
    op.execute("DROP RULE IF EXISTS learning_labels_no_update ON learning_labels")
    op.execute("DROP RULE IF EXISTS approval_gates_no_delete ON approval_gates")
    for t in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
