"""NirvanaI — conversations, messages, document drafts, model usage (Phase 6)

Depends on 005. Adds the four NirvanaI tables (fail-closed RLS NULLIF + FORCE),
makes `model_usage_events` append-only, and generalizes the Phase-4
`contract_embeddings` table into `memory_embeddings` (source/source_id discriminator
+ HNSW ANN index for <3s retrieval).

Revision ID: 006
Revises: 005
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ["nirvana_conversations", "nirvana_messages", "document_drafts", "model_usage_events"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE nirvana_conversations (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id      UUID NOT NULL REFERENCES tenants(id),
            user_id        UUID NOT NULL REFERENCES users(id),
            title          TEXT,
            module_context TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_nirvana_conversations_user ON nirvana_conversations (user_id)")

    op.execute(
        """
        CREATE TABLE nirvana_messages (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            conversation_id UUID NOT NULL REFERENCES nirvana_conversations(id),
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            intent          TEXT,
            citations       JSONB NOT NULL DEFAULT '[]',
            grounded        BOOLEAN,
            model_used      TEXT,
            run_id          UUID REFERENCES agent_runs(run_id),
            latency_ms      INTEGER,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_nirvana_messages_conv ON nirvana_messages (conversation_id, created_at)")

    op.execute(
        """
        CREATE TABLE document_drafts (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            user_id         UUID NOT NULL REFERENCES users(id),
            conversation_id UUID REFERENCES nirvana_conversations(id),
            template        TEXT NOT NULL,
            context_ref     JSONB NOT NULL,
            title           TEXT NOT NULL,
            body_markdown   TEXT NOT NULL,
            citations       JSONB NOT NULL DEFAULT '[]',
            status          TEXT NOT NULL DEFAULT 'draft',
            sent_by         UUID REFERENCES users(id),
            sent_at         TIMESTAMPTZ,
            run_id          UUID REFERENCES agent_runs(run_id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_document_drafts_tenant ON document_drafts (tenant_id, created_at DESC)")

    op.execute(
        """
        CREATE TABLE model_usage_events (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id          UUID NOT NULL REFERENCES tenants(id),
            model              TEXT NOT NULL,
            purpose            TEXT NOT NULL,
            input_tokens       INTEGER NOT NULL,
            output_tokens      INTEGER NOT NULL,
            cache_read_tokens  INTEGER NOT NULL DEFAULT 0,
            cost_usd           NUMERIC(12,6) NOT NULL,
            cache_hit          BOOLEAN NOT NULL DEFAULT FALSE,
            run_id             UUID REFERENCES agent_runs(run_id),
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_model_usage_tenant_day ON model_usage_events (tenant_id, created_at)")

    # Fail-closed RLS + FORCE on every new table (consistent with prior phases).
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

    # model_usage_events is append-only (audit/billing integrity).
    op.execute("CREATE RULE model_usage_no_update AS ON UPDATE TO model_usage_events DO INSTEAD NOTHING")
    op.execute("CREATE RULE model_usage_no_delete AS ON DELETE TO model_usage_events DO INSTEAD NOTHING")

    # Generalize the Phase-4 embedding table: contracts/clauses AND interactions/opportunities.
    op.execute("ALTER TABLE contract_embeddings RENAME TO memory_embeddings")
    op.execute("ALTER TABLE memory_embeddings ADD COLUMN source TEXT NOT NULL DEFAULT 'contract'")
    op.execute("ALTER TABLE memory_embeddings ADD COLUMN source_id UUID")
    # Backfill source_id for the existing contract chunks (authorizable record = contract).
    op.execute("UPDATE memory_embeddings SET source_id = contract_id WHERE source_id IS NULL")
    # Replace the IVFFlat ANN index with HNSW (better recall/latency for <3s retrieval).
    op.execute("DROP INDEX IF EXISTS idx_contract_embeddings_ann")
    op.execute(
        "CREATE INDEX ix_memory_embeddings_vec ON memory_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_memory_embeddings_scope ON memory_embeddings (tenant_id, source)")
    op.execute("CREATE INDEX ix_memory_embeddings_source_id ON memory_embeddings (source_id)")


def downgrade() -> None:
    # Revert the embedding-table generalization.
    op.execute("DROP INDEX IF EXISTS ix_memory_embeddings_source_id")
    op.execute("DROP INDEX IF EXISTS ix_memory_embeddings_scope")
    op.execute("DROP INDEX IF EXISTS ix_memory_embeddings_vec")
    op.execute("ALTER TABLE memory_embeddings DROP COLUMN IF EXISTS source_id")
    op.execute("ALTER TABLE memory_embeddings DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE memory_embeddings RENAME TO contract_embeddings")
    op.execute(
        "CREATE INDEX idx_contract_embeddings_ann ON contract_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.execute("DROP RULE IF EXISTS model_usage_no_delete ON model_usage_events")
    op.execute("DROP RULE IF EXISTS model_usage_no_update ON model_usage_events")
    for t in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
