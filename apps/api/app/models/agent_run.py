"""AgentRun — immutable audit backbone (§5.4).

No TenantScopedMixin: the PK is `run_id` and a run transitions status exactly
once (running → terminal). DELETE is blocked and terminal rows are frozen by DB
rules/trigger in Migration 001.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    run_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True)
    agent: Mapped[str]
    trigger: Mapped[str]
    status: Mapped[str] = mapped_column(default="running")
    actor: Mapped[str] = mapped_column(default="ai")
    actor_user_id: Mapped[UUID | None]
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    inputs_ref: Mapped[str | None]
    outputs_ref: Mapped[str | None]
    parent_run_id: Mapped[UUID | None]
    correlation_id: Mapped[str | None] = mapped_column(index=True)
    error_message: Mapped[str | None]
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
