"""Graceful-degradation tracking (§15.1). The read/analysis path depends only on the P4
memory layer + deterministic services, so the app stays usable when an agent, the model
provider, ClickHouse, or a connector is down. This service records which subsystems are
currently degraded and exposes them via `/health/degradation`.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("degradation")

# Known subsystems and the human-facing degraded behavior (§15.1 matrix).
DEGRADED_BEHAVIOR: dict[str, str] = {
    "model_provider": "NirvanaI Q&A/drafts disabled; Commitment Check + all analysis still work",
    "clickhouse": "Drilldowns serve cached/sampled aggregates; dashboard KPIs unaffected",
    "connector": "Source shows 'reconnect'; memory serves last sync",
    "redis": "Reads fall through to Postgres memory snapshot (slower but correct)",
    "agent_runtime": "New syncs/automation queue; all reads + Commitment Check still work",
}


class DegradationService:
    """In-process registry of degraded subsystems. Process-local by design: each pod reports
    what it observes; the union across pods is the platform view."""

    def __init__(self) -> None:
        self._degraded: dict[str, str] = {}

    def mark_degraded(self, subsystem: str, reason: str | None = None) -> None:
        self._degraded[subsystem] = reason or DEGRADED_BEHAVIOR.get(subsystem, "degraded")
        logger.warning("degradation.marked subsystem=%s reason=%s", subsystem, reason)

    def mark_healthy(self, subsystem: str) -> None:
        self._degraded.pop(subsystem, None)

    def is_degraded(self, subsystem: str) -> bool:
        return subsystem in self._degraded

    def snapshot(self) -> dict:
        return {
            "degraded": [
                {
                    "subsystem": s,
                    "reason": reason,
                    "behavior": DEGRADED_BEHAVIOR.get(s, "degraded"),
                }
                for s, reason in sorted(self._degraded.items())
            ],
            "healthy": not self._degraded,
        }


degradation_service = DegradationService()
