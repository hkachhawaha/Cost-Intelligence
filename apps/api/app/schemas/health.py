from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str  # "ok"
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str  # "ready" | "degraded"
    postgres: bool
    redis: bool
