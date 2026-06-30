"""Per-tenant quotas + circuit breakers (§13.3, §10.3). Protect the platform from a single
tenant's runaway sync/query/LLM usage, and contain downstream failures (model provider,
ClickHouse, connector) by degrading gracefully rather than failing globally.

The `CircuitBreaker` is in-process (no external state) so callers always have a local guard;
the persisted `breaker_open` flag on `tenant_quotas` is the durable, cross-process signal.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.commitment import TenantQuota

logger = logging.getLogger("quotas")

T = TypeVar("T")


class QuotaExceeded(Exception):
    """A tenant exceeded a configured quota (QPS / tokens / rows)."""


class CircuitOpen(Exception):
    """The tenant's durable breaker is open — serve cached/degraded results."""


class QuotaService:
    """Reads the tenant's quota row and enforces it. QPS/token counters use Redis when
    available and degrade to permissive (the durable breaker flag still applies)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _quota(self, tenant_id: str) -> TenantQuota | None:
        return await self.session.scalar(
            select(TenantQuota).where(TenantQuota.tenant_id == UUID(tenant_id))
        )

    async def check_query(self, tenant_id: str) -> None:
        q = await self._quota(tenant_id)
        if q is None:
            return  # no quota row → default-permissive
        if q.breaker_open:
            raise CircuitOpen("tenant breaker open — serving cached/degraded results")
        if await self._qps(tenant_id) > q.max_query_qps:
            raise QuotaExceeded("query QPS quota exceeded")

    async def check_llm(self, tenant_id: str, tokens: int) -> None:
        q = await self._quota(tenant_id)
        if q is None:
            return
        if await self._tokens_today(tenant_id) + tokens > q.max_llm_tokens_day:
            raise QuotaExceeded("daily LLM token quota exceeded")

    async def _qps(self, tenant_id: str) -> int:
        """Best-effort per-second request counter via Redis; 0 if Redis is unavailable."""
        try:
            from app.core.redis import get_redis

            redis = get_redis()
            window = int(time.time())
            key = f"qps:{tenant_id}:{window}"
            n = await redis.incr(key)
            await redis.expire(key, 2)
            await redis.aclose()
            return int(n)
        except Exception:  # noqa: BLE001 — counter is best-effort
            return 0

    async def _tokens_today(self, tenant_id: str) -> int:
        try:
            from app.core.redis import get_redis

            redis = get_redis()
            val = await redis.get(f"llm_tokens:{tenant_id}")
            await redis.aclose()
            return int(val) if val else 0
        except Exception:  # noqa: BLE001
            return 0


class CircuitBreaker:
    """In-process breaker. Trips after `breaker_failure_threshold` consecutive failures for a
    named subsystem; while open, `call` serves the fallback instead of erroring. Resets after
    `breaker_reset_seconds` (half-open: the next call is allowed through to probe recovery)."""

    def __init__(
        self,
        failure_threshold: int | None = None,
        reset_seconds: int | None = None,
    ):
        self.failure_threshold = failure_threshold or settings.breaker_failure_threshold
        self.reset_seconds = reset_seconds or settings.breaker_reset_seconds
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def _is_open(self, name: str) -> bool:
        opened = self._opened_at.get(name)
        if opened is None:
            return False
        if (time.monotonic() - opened) >= self.reset_seconds:
            # Half-open: allow one probe through; clear the open marker.
            self._opened_at.pop(name, None)
            self._failures[name] = 0
            return False
        return True

    def _record_success(self, name: str) -> None:
        self._failures[name] = 0
        self._opened_at.pop(name, None)

    def _record_failure(self, name: str) -> None:
        self._failures[name] = self._failures.get(name, 0) + 1

    def _should_open(self, name: str) -> bool:
        return self._failures.get(name, 0) >= self.failure_threshold

    async def call(
        self, name: str, fn: Callable[[], Awaitable[T]], fallback: Callable[[], Awaitable[T]]
    ) -> T:
        if self._is_open(name):
            return await fallback()
        try:
            result = await fn()
            self._record_success(name)
            return result
        except Exception:  # noqa: BLE001 — any downstream failure trips the breaker
            self._record_failure(name)
            if self._should_open(name):
                self._open(name)
            return await fallback()

    def _open(self, name: str) -> None:
        self._opened_at[name] = time.monotonic()
        logger.warning("breaker.open subsystem=%s failures=%d", name, self._failures.get(name, 0))


# Module-level breaker shared across the read path (model gateway, ClickHouse, connectors).
circuit_breaker = CircuitBreaker()
