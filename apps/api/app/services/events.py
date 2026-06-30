"""Redis Streams event publisher.

Wraps every event in the standard envelope (event_id, schema_version, timestamp)
and appends to `stream:<event>`. Consumers (Phase 2 matching, Phase 7 steward)
read with per-consumer groups.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import redis.asyncio as aioredis

from app.core.config import settings

SCHEMA_VERSIONS = {"records.landed": 1, "data_quality.schema_drift": 1}


async def publish_event(event: str, payload: dict) -> str:
    event_id = str(uuid4())
    envelope = {
        "event_id": event_id,
        "schema_version": SCHEMA_VERSIONS.get(event, 1),
        "timestamp": datetime.now(UTC).isoformat(),
        **payload,
    }
    # Short-lived client per publish: avoids binding a module-level client to one
    # event loop (which breaks across Celery `asyncio.run` and per-test loops).
    client = aioredis.from_url(str(settings.redis_url))
    try:
        await client.xadd(f"stream:{event}", {"data": json.dumps(envelope)})
    finally:
        await client.aclose()
    return event_id
