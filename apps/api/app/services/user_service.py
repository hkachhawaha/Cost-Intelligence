"""User service — just-in-time provisioning from Auth0 claims.

On first login the frontend calls POST /api/v1/auth/sync; this upserts the
local `users` row (bridging Auth0 → canonical user) and stamps last_login_at.
Runs inside the tenant-scoped session, so RLS guarantees the row belongs to the
caller's tenant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.models.user import User


async def sync_user(session: AsyncSession, principal: Principal) -> tuple[str, bool]:
    """Upsert the user identified by the JWT. Returns (user_id, created)."""
    existing = (
        await session.execute(select(User).where(User.auth0_id == principal.user_id))
    ).scalar_one_or_none()

    if existing is not None:
        existing.last_login_at = datetime.now(UTC)
        await session.flush()
        return str(existing.id), False

    user = User(
        tenant_id=UUID(principal.tenant_id),
        auth0_id=principal.user_id,
        email=principal.email or "",
        entity_id=UUID(principal.entity_id) if principal.entity_id else None,
        last_login_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    return str(user.id), True
