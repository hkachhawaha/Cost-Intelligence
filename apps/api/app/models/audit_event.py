"""AuditEvent — fully immutable (no UPDATE, no DELETE; enforced by DB rules)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID | None] = mapped_column(index=True)
    tenant_id: Mapped[UUID] = mapped_column(index=True)
    event_type: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    actor: Mapped[str] = mapped_column(default="ai")
    actor_user_id: Mapped[UUID | None]
    request_id: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
