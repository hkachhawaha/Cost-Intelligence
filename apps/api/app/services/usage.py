"""Per-tenant, per-call model cost attribution (§14.2).

`record_model_usage` writes one append-only `model_usage_events` row per LLM call
(or cache hit). Cost is computed in CODE (never by the model) from the gateway's
price table. Best-effort: a usage-write failure must never break a user-facing call,
so it opens its own RLS-bound session and swallows errors with a warning.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from app.core.database import session_for_tenant
from app.models.nirvana import ModelUsageEvent

logger = logging.getLogger("model_usage")


async def record_model_usage(
    *,
    tenant_id: str,
    model: str,
    purpose: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cost_usd: Decimal,
    cache_hit: bool = False,
    run_id: str | None = None,
) -> None:
    try:
        async with await session_for_tenant(tenant_id) as session:
            session.add(
                ModelUsageEvent(
                    tenant_id=UUID(tenant_id),
                    model=model,
                    purpose=purpose,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read_tokens,
                    cost_usd=cost_usd,
                    cache_hit=cache_hit,
                    run_id=UUID(run_id) if run_id else None,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001 — usage attribution is non-fatal to the call
        logger.warning("record_model_usage failed tenant=%s purpose=%s", tenant_id, purpose)
