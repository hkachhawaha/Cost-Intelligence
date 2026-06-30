"""Opportunity ranking (§11.2).

Primary:   impact × confidence  (descending)
Secondary: time_sensitivity      (descending; closer deadlines first)
Tertiary:  effort                (ascending; quick wins first)
All deterministic; no LLM.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.rules._types import RuleFinding


class ScoringService:
    def rank(self, findings: list[RuleFinding]) -> list[RuleFinding]:
        return sorted(
            findings,
            key=lambda f: (f.impact * f.confidence, f.time_sensitivity, -f.effort),
            reverse=True,
        )

    @staticmethod
    def rank_score(f: RuleFinding) -> Decimal:
        return (f.impact * f.confidence).quantize(Decimal("0.0001"))
