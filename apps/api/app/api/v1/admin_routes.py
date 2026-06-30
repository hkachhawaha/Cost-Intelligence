"""Scalability/ops admin API (§6.3) — per-tenant quotas + circuit-breaker state. Admin only.

Quota rows default-permissive when absent; POST upserts. The breaker flag here is the durable
cross-process signal that read paths honor (see `QuotaService.check_query`).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.config import settings
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.commitment import TenantQuota

router = APIRouter(prefix="/admin", tags=["admin"])


class QuotaUpdate(BaseModel):
    max_spend_rows: int | None = None
    max_llm_tokens_day: int | None = None
    max_concurrent_syncs: int | None = None
    max_query_qps: int | None = None
    breaker_open: bool | None = None
    breaker_reason: str | None = None


def _quota_obj(q: TenantQuota) -> dict:
    return {
        "tenant_id": str(q.tenant_id),
        "max_spend_rows": q.max_spend_rows,
        "max_llm_tokens_day": q.max_llm_tokens_day,
        "max_concurrent_syncs": q.max_concurrent_syncs,
        "max_query_qps": q.max_query_qps,
        "breaker_open": q.breaker_open,
        "breaker_reason": q.breaker_reason,
    }


async def _get_quota(session: AsyncSession, tenant_id: str) -> TenantQuota | None:
    return await session.scalar(
        select(TenantQuota).where(TenantQuota.tenant_id == UUID(tenant_id))
    )


@router.get("/quotas/{tenant_id}", dependencies=[Depends(require_permission("admin:read"))])
async def get_quota(tenant_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    q = await _get_quota(session, tenant_id)
    if q is None:
        # Default-permissive view (no row persisted yet).
        return {
            "tenant_id": tenant_id,
            "max_spend_rows": settings.default_max_spend_rows,
            "max_llm_tokens_day": settings.default_max_llm_tokens_day,
            "max_concurrent_syncs": 2,
            "max_query_qps": settings.default_max_query_qps,
            "breaker_open": False,
            "breaker_reason": None,
        }
    return _quota_obj(q)


@router.post(
    "/quotas/{tenant_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("admin:write"))],
)
async def update_quota(
    tenant_id: str,
    body: QuotaUpdate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    q = await _get_quota(session, tenant_id)
    if q is None:
        q = TenantQuota(
            id=uuid4(),
            tenant_id=UUID(tenant_id),
            max_spend_rows=settings.default_max_spend_rows,
            max_llm_tokens_day=settings.default_max_llm_tokens_day,
            max_query_qps=settings.default_max_query_qps,
        )
        session.add(q)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(q, field, value)
    await session.commit()
    return _quota_obj(q)
