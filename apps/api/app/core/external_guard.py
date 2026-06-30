"""First-party guard (§3.4). The external-intelligence flag is platform-enforced OFF in
v1–v3; any benchmark/should-cost/CPI-fairness ask returns the out-of-scope message."""

from __future__ import annotations

from app.core.config import settings

REQUIRES_EXTERNAL_DATA_MSG = (
    "This question requires external market data, which is outside the scope of "
    "Terzo Cost Intelligence v3."
)


def external_intelligence_available() -> bool:
    """Default False; platform-enforced in v1–v3 (the seam is never wired)."""
    return settings.external_intelligence_enabled
