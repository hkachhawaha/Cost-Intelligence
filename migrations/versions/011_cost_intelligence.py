"""Cost Intelligence storage — connected Google Sheet config + versioned Agent Memory snapshot

Single-workspace, Sheets-driven realignment. These tables are NOT tenant-scoped (no RLS): the
product runs as one workspace whose data is the connected spreadsheet.

Revision ID: 011
Revises: 010
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ci_data_source (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            spreadsheet_id   TEXT NOT NULL UNIQUE,
            spreadsheet_url  TEXT NOT NULL,
            spreadsheet_name TEXT,
            status           TEXT NOT NULL DEFAULT 'never',
            last_synced_at   TIMESTAMPTZ,
            total_records    BIGINT NOT NULL DEFAULT 0,
            last_error       TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ci_memory_snapshot (
            id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            version    INT NOT NULL,
            payload    JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_ci_snapshot_version ON ci_memory_snapshot (version DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ci_memory_snapshot CASCADE")
    op.execute("DROP TABLE IF EXISTS ci_data_source CASCADE")
