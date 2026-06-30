"""Shared output type for every detection rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID


@dataclass
class RuleFinding:
    """The output of a detection rule. Carries everything needed to upsert an
    Opportunity, plus the evidence dict that makes the figure auditable (§7.3)."""

    type: str  # 'maverick'|'overspend'|...
    bucket: str  # 'savings'|'recovery'|'control'
    impact: Decimal  # the $ figure — CODE-computed, never LLM
    confidence: Decimal  # inherited from MatchResult (min-of-chain)
    contract_id: UUID | None  # dedup key with `type`; None for tenant-wide
    vendor_id: UUID | None = None  # optional; set by some rules
    evidence: dict = field(default_factory=dict)
    time_sensitivity: int = 0  # 0–100; secondary rank factor
    effort: int = 50  # 0–100; secondary rank factor (lower = easier)
    recovery_items: list[dict] = field(default_factory=list)
