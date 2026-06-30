"""External-intelligence seam (§3.4). INTERFACE ONLY — NO IMPLEMENTATION in v1–v3.

This ABC documents the future integration point for external market/benchmark data WITHOUT
compromising the first-party guarantee. It is never subclassed in v1–v3, and all call sites
are guarded by the `external_intelligence_enabled` feature flag (default False,
platform-enforced). Adding a real implementation later is purely additive and does not touch
any first-party detection/matching/scoring code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class ExternalBenchmarkBase(ABC):
    """Future seam for external benchmarks. DO NOT implement in v1–v3."""

    @abstractmethod
    async def market_rate(self, sku: str, region: str, currency: str) -> Decimal:
        """Would return an external market unit rate for a SKU. Not implemented."""
        raise NotImplementedError("external intelligence is out of scope (v1–v3)")

    @abstractmethod
    async def peer_benchmark(self, category: str, spend: Decimal) -> dict:
        """Would return peer-benchmark percentiles. Not implemented."""
        raise NotImplementedError("external intelligence is out of scope (v1–v3)")

    @abstractmethod
    async def index_forecast(self, index_type: str, horizon_months: int) -> Decimal:
        """Would return a forecast index move (replacing the first-party assumption).
        Not implemented — Commitment Check uses a first-party assumption (§8.6)."""
        raise NotImplementedError("external intelligence is out of scope (v1–v3)")
