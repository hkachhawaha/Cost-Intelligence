"""Redis client helper. Returns a fresh asyncio client bound to the caller's
event loop (avoids cross-loop reuse issues in Celery `asyncio.run` and per-test
loops). Callers should close it, or let it be GC'd at loop teardown."""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings


def get_redis() -> aioredis.Redis:
    return aioredis.from_url(str(settings.redis_url))
