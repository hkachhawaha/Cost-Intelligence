"""Phase 9 — agentic automation, connectors, and continuous learning models.

`Task` + `ApprovalGate` are the gated-automation backbone: no external action without an
approved gate (§5.1). `approval_gates` (no delete) and `learning_labels` (no update/delete)
are immutable audit surfaces. All tenant-scoped (RLS).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin


class Task(Base, TenantScopedMixin):
    __tablename__ = "tasks"

    opportunity_id: Mapped[UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    title: Mapped[str]
    description: Mapped[str | None]
    type: Mapped[str]  # non_renewal|renegotiation|recovery|review
    status: Mapped[str] = mapped_column(String, default="open", index=True)
    priority: Mapped[str] = mapped_column(String, default="normal")
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[str] = mapped_column(String, default="ai")  # ai|human
    due_date: Mapped[date | None]
    reminder_at: Mapped[datetime | None]
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    draft_document_id: Mapped[UUID | None] = mapped_column(ForeignKey("document_drafts.id"))
    workflow_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))
    langgraph_thread_id: Mapped[str | None]
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    approvals: Mapped[list[ApprovalGate]] = relationship(back_populates="task")


class ApprovalGate(Base, TenantScopedMixin):
    """Persisted HITL decision; the only thing that authorizes an external action."""

    __tablename__ = "approval_gates"

    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    workflow_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))
    action_type: Mapped[str]  # external_send|cancel_contract|...
    action_payload: Mapped[dict] = mapped_column(JSONB)
    decision: Mapped[str] = mapped_column(String, default="pending")  # pending|approved|rejected
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None]
    decision_note: Mapped[str | None]

    task: Mapped[Task] = relationship(back_populates="approvals")


class TaskReminder(Base, TenantScopedMixin):
    __tablename__ = "task_reminders"

    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    fire_at: Mapped[datetime]
    channel: Mapped[str] = mapped_column(String, default="email")  # email|slack|in_app
    sent: Mapped[bool] = mapped_column(Boolean, default=False)


class ConnectorCredential(Base, TenantScopedMixin):
    __tablename__ = "connector_credentials"

    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"))
    connector_type: Mapped[str]  # coupa|oracle|sap
    auth_type: Mapped[str]  # oauth2|service_account|keystore
    secret_ref: Mapped[str]  # KMS ref, NEVER the raw secret
    oauth_state: Mapped[str | None]
    token_expires_at: Mapped[datetime | None]
    scopes: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|active|expired|revoked


class LearningLabel(Base, TenantScopedMixin):
    """Continuous-learning signal — immutable (append-only)."""

    __tablename__ = "learning_labels"

    signal_type: Mapped[str] = mapped_column(index=True)
    subject_id: Mapped[UUID]
    features: Mapped[dict] = mapped_column(JSONB)
    label: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class ModelCalibration(Base, TenantScopedMixin):
    """Versioned learned parameters; activation is atomic, prior retained for rollback."""

    __tablename__ = "model_calibration"

    model_kind: Mapped[str]  # fuzzy_weights|detection_thresholds|anomaly_if
    version: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(JSONB)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
