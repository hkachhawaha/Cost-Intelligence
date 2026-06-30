"""POST /api/v1/auth/sync — just-in-time user provisioning.

Called by the frontend right after login; upserts the local `users` row from the
verified JWT claims and records an audit event.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.schemas.auth import SyncUserResponse
from app.services.user_service import sync_user

router = APIRouter()


@router.post("/auth/sync", response_model=SyncUserResponse)
async def sync(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> SyncUserResponse:
    user_id, created = await sync_user(session, principal)
    await record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        event_type="user_logged_in",
        payload={"auth0_id": principal.user_id, "created": created},
        actor="human",
    )
    return SyncUserResponse(user_id=user_id, created=created)
