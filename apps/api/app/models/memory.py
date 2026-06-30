"""Memory-layer models (Phase 4): TenantMemory (Store 1), ContractEmbedding
(Store 2 / pgvector), and SyncRun bookkeeping.

`TenantMemory` is the durable source of truth for the Redis KPI cache. Every
numeric field is computed in Python by `KpiComputer` (determinism for money, §5.6).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class TenantMemory(Base):
    """Structured intelligence snapshot — one row per tenant (Store 1)."""

    __tablename__ = "tenant_memory"

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)

    # Sync lifecycle / staleness
    last_synced_at: Mapped[datetime]
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    memory_version: Mapped[int] = mapped_column(Integer, default=1)
    build_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_fingerprint: Mapped[str | None] = mapped_column(Text)

    # Headline KPIs (Decimal; never float, never LLM-computed)
    total_spend: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    spend_under_management_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    contract_compliance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    po_coverage_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    match_coverage_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    total_savings: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    total_recovery: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    total_identified: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    total_realized: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    opportunity_count: Mapped[int] = mapped_column(Integer, default=0)
    contract_count: Mapped[int] = mapped_column(Integer, default=0)
    vendor_count: Mapped[int] = mapped_column(Integer, default=0)
    spend_record_count: Mapped[int] = mapped_column(Integer, default=0)

    # Pre-computed summary blobs (read directly by UI modules in Phase 5)
    opportunity_count_by_type: Mapped[dict] = mapped_column(JSONB, default=dict)
    opportunity_amount_by_type: Mapped[dict] = mapped_column(JSONB, default=dict)
    top_opportunities: Mapped[list] = mapped_column(JSONB, default=list)
    vendor_summary: Mapped[list] = mapped_column(JSONB, default=list)
    renewal_calendar: Mapped[dict] = mapped_column(JSONB, default=dict)
    spend_by_category: Mapped[list] = mapped_column(JSONB, default=list)
    spend_by_cost_center: Mapped[list] = mapped_column(JSONB, default=list)
    spend_trend: Mapped[list] = mapped_column(JSONB, default=list)
    match_coverage_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)
    data_quality_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    alerts: Mapped[list] = mapped_column(JSONB, default=list)
    kpi_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class MemoryEmbedding(Base, TenantScopedMixin):
    """Vector store — one row per text chunk (Store 2). Queried by NirvanaI RAG (Phase 6).

    Generalized in Migration 006 from `contract_embeddings` to `memory_embeddings`: it now
    holds contract/clause chunks AND (later) interaction/opportunity chunks, discriminated by
    `source` + `source_id`. `source_id` is the authorizable record (the contract id for
    contract/clause chunks) so RBAC scoping filters on it before the vector search.
    """

    __tablename__ = "memory_embeddings"

    contract_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("contracts.id"), index=True
    )
    clause_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source: Mapped[str] = mapped_column(
        String, default="contract"
    )  # contract|clause|interaction|opportunity
    source_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_type: Mapped[str] = mapped_column(String, default="contract")
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    model: Mapped[str] = mapped_column(String, default="gemini-embedding-001")
    memory_version: Mapped[int] = mapped_column(Integer, default=1)


# Backwards-compatible alias (the Phase-4 name) so existing imports keep working.
ContractEmbedding = MemoryEmbedding


class SyncRun(Base, TenantScopedMixin):
    """User-facing sync run; links to underlying agent_runs via build_run_id."""

    __tablename__ = "sync_runs"

    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String)  # 'initial'|'refresh'
    status: Mapped[str] = mapped_column(String, default="running")
    celery_task_id: Mapped[str | None] = mapped_column(String)
    stage: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
