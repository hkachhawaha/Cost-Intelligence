"""GET /api/v1/me — returns the authenticated principal.

The first end-to-end proof that Auth0 validation + tenant binding work.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import Principal, get_current_principal
from app.schemas.me import MeResponse

router = APIRouter()


@router.get("/me", response_model=MeResponse)
async def me(principal: Principal = Depends(get_current_principal)) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        email=principal.email,
        role=principal.role,
        entity_id=principal.entity_id,
        permissions=list(principal.permissions),
    )
