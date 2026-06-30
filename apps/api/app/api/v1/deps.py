"""Shared FastAPI dependencies for the Phase-5 read endpoints."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.kpi_cache import RedisKpiCache
from app.core.redis import get_redis
from app.services.memory import MemoryService
from app.services.memory_kpis import KpiComputer
from app.services.read_models import ReadModelService


def get_read_models(session: AsyncSession = Depends(get_session)) -> ReadModelService:
    """Build the read-model service chain (memory-first, canonical drill-downs)."""
    memory = MemoryService(session, RedisKpiCache(get_redis()), KpiComputer(session))
    return ReadModelService(session, memory)
