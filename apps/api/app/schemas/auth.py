from __future__ import annotations

from pydantic import BaseModel


class SyncUserResponse(BaseModel):
    user_id: str
    created: bool  # true if a new row was inserted
