"""SkuNormalizationService — map invoice/contract SKU variants → a canonical SKU.

Deterministic-first: uppercase, strip noise, collapse separators. That canonical form is
stable and free; an LLM refinement is available but optional (and lazy) for the long tail.
"""

from __future__ import annotations

import re

_NOISE = re.compile(r"[^A-Z0-9]+")


class SkuNormalizationService:
    def canonical_form(self, raw_sku: str, description: str | None = None) -> str:
        """Deterministic canonicalization: a stable, comparable SKU key."""
        base = (raw_sku or description or "").upper().strip()
        base = _NOISE.sub("-", base).strip("-")
        return base or "UNKNOWN"

    async def canonicalize(
        self, tenant_id: str, raw_sku: str, description: str | None = None
    ) -> str:
        # v1.5 uses the deterministic form (free, stable). An LLM/fuzzy pass over the
        # tenant's existing canonical SKUs can refine this later (kept out of the hot path).
        return self.canonical_form(raw_sku, description)


sku_normalization_service = SkuNormalizationService()
