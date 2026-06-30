"""Liveness (`/healthz`) and readiness (`/readyz`) probes.

`/healthz` returns ok if the process is up. `/readyz` pings Postgres and Redis
so orchestrators only route traffic when dependencies are reachable.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionFactory
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0", environment=settings.environment)


@router.get("/health/degradation", tags=["health"])
async def degradation() -> dict:
    """Which subsystems are currently degraded (§15.1). The read/analysis path stays usable
    even when the model provider, ClickHouse, an agent, or a connector is degraded."""
    from app.core.degradation import degradation_service

    return degradation_service.snapshot()


@router.get("/readyz", response_model=ReadinessResponse, tags=["health"])
async def readyz(response: Response) -> ReadinessResponse:
    pg_ok = await _check_postgres()
    redis_ok = await _check_redis()
    ready = pg_ok and redis_ok
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready else "degraded", postgres=pg_ok, redis=redis_ok
    )


async def _check_postgres() -> bool:
    try:
        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


async def _check_redis() -> bool:
    try:
        client = aioredis.from_url(str(settings.redis_url))
        await client.ping()
        await client.aclose()
        return True
    except Exception:  # noqa: BLE001
        return False
