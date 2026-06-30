from __future__ import annotations

from pydantic import BaseModel


class MeResponse(BaseModel):
    user_id: str
    tenant_id: str
    email: str | None
    role: str | None
    entity_id: str | None
    permissions: list[str]
