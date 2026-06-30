"""Event bus abstraction (§4, §7) — domain events for the agent fabric.

Redis Streams is the default transport (already a hard dependency). Kafka is an optional
upgrade path used for high-throughput / cross-service fan-out; `DualWriteBus` lets a tenant
migrate by writing to both during cutover. The Kafka backend lazy-imports its client so the
package is optional, and dual-write tolerates a secondary failure (primary is source of truth).
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger("eventbus")


class EventBus(ABC):
    @abstractmethod
    async def publish(self, topic: str, event: dict) -> str | None:
        """Publish one event; returns a transport message id (or None)."""

    async def close(self) -> None:  # optional cleanup
        return None


class RedisStreamsBus(EventBus):
    """XADD onto a per-topic stream. Values are JSON-encoded under the `data` field."""

    def __init__(self):
        self._redis = None

    async def _client(self):
        if self._redis is None:
            self._redis = get_redis()
        return self._redis

    async def publish(self, topic: str, event: dict) -> str | None:
        client = await self._client()
        msg_id = await client.xadd(f"events:{topic}", {"data": json.dumps(event, default=str)})
        return msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


class KafkaBus(EventBus):
    """Optional Kafka transport. The client is lazy-imported so `aiokafka` stays optional;
    if it isn't installed, `publish` logs and no-ops (returns None) rather than crashing."""

    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._producer: Any | None = None

    def _producer_cls(self):
        try:
            from aiokafka import AIOKafkaProducer
        except ImportError:
            return None
        return AIOKafkaProducer

    async def publish(self, topic: str, event: dict) -> str | None:
        cls = self._producer_cls()
        if cls is None:
            logger.warning("eventbus.kafka_absent topic=%s (event dropped from kafka leg)", topic)
            return None
        if self._producer is None:
            self._producer = cls(bootstrap_servers=self.bootstrap_servers)
            await self._producer.start()
        await self._producer.send_and_wait(
            f"events.{topic}", json.dumps(event, default=str).encode("utf-8")
        )
        return "kafka-ack"

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None


class DualWriteBus(EventBus):
    """Write to a primary (source of truth) and best-effort to a secondary. A secondary
    failure is logged but never fails the publish — used during a Redis→Kafka migration."""

    def __init__(self, primary: EventBus, secondary: EventBus):
        self.primary = primary
        self.secondary = secondary

    async def publish(self, topic: str, event: dict) -> str | None:
        msg_id = await self.primary.publish(topic, event)  # must succeed
        try:
            await self.secondary.publish(topic, event)
        except Exception as exc:  # noqa: BLE001 — secondary is best-effort during cutover
            logger.warning("eventbus.secondary_publish_failed topic=%s err=%s", topic, exc)
        return msg_id

    async def close(self) -> None:
        await self.primary.close()
        await self.secondary.close()


def get_event_bus() -> EventBus:
    """Construct the configured bus. `event_bus_mode`: redis | kafka | dual."""
    mode = settings.event_bus_mode
    if mode == "kafka":
        return KafkaBus(settings.kafka_bootstrap_servers)
    if mode == "dual":
        return DualWriteBus(
            RedisStreamsBus(), KafkaBus(settings.kafka_bootstrap_servers)
        )
    return RedisStreamsBus()
