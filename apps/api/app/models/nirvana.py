"""Phase 6 — NirvanaI models: conversations, messages, document drafts, model-usage.

All tenant-scoped (RLS). `model_usage_events` is append-only (audit/billing integrity,
enforced by DB rules in Migration 006). `document_drafts.sent_by`/`sent_at` are set ONLY
by a human PATCH — the platform never auto-sends (§5.7, §11.5).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class NirvanaConversation(Base, TenantScopedMixin):
    """A NirvanaI thread, scoped to a user within a tenant."""

    __tablename__ = "nirvana_conversations"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str | None]
    module_context: Mapped[str | None]


class NirvanaMessage(Base, TenantScopedMixin):
    """One turn — a user message OR an assistant message. Citations live on assistant turns."""

    __tablename__ = "nirvana_messages"

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("nirvana_conversations.id"), index=True
    )
    role: Mapped[str]  # 'user'|'assistant'
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None]  # 'qa'|'document'|'out_of_scope'
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    grounded: Mapped[bool | None] = mapped_column(Boolean)
    model_used: Mapped[str | None]
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class DocumentDraft(Base, TenantScopedMixin):
    """A generated document draft. Never auto-sent (§5.7)."""

    __tablename__ = "document_drafts"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("nirvana_conversations.id"))
    template: Mapped[str]
    context_ref: Mapped[dict] = mapped_column(JSONB)
    title: Mapped[str]
    body_markdown: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(default="draft")  # draft|edited|sent|discarded
    sent_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None]
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))


class ModelUsageEvent(Base, TenantScopedMixin):
    """Per-tenant, per-call model cost attribution (§14.2). Append-only."""

    __tablename__ = "model_usage_events"

    model: Mapped[str]
    purpose: Mapped[str]
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6))
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))
