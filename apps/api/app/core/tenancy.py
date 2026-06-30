"""Async-safe tenant context + RLS binding.

The verified tenant id is held in a ContextVar (per-request / per-task, async
safe). `apply_rls` pushes it into the Postgres session as a transaction-local
setting that every RLS policy reads. Default None ⇒ RLS fails closed (0 rows).
"""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

current_tenant: ContextVar[str | None] = ContextVar("current_tenant", default=None)
current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)


async def apply_rls(session: AsyncSession, tenant_id: str | UUID) -> None:
    """Set the Postgres session var every RLS policy reads.

    The third arg ``true`` makes it transaction-local — Postgres resets it on
    commit/rollback, so a pooled connection never carries one tenant's id into
    another tenant's transaction (the classic multi-tenant footgun).
    """
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tid, true)"),
        {"tid": str(tenant_id)},
    )


def set_tenant(tenant_id: str | None) -> None:
    current_tenant.set(tenant_id)


def get_tenant() -> str | None:
    return current_tenant.get()
