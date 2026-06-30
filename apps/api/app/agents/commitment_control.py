"""Commitment Control agent (L1, ADVISORY, deterministic) — §8.6.

`stress_test` models a proposed deal's indexed exposure under adverse index moves and returns
an approve/condition/block verdict against the entity's margin tolerance:

  indexed_exposure = ACV × indexed_share × (1 + assumed_index_pct)
  for each adverse move m in {5, 10, 15}%:
      scenario_exposure(m) = indexed_exposure × (1 + m/100)

The index move is a FIRST-PARTY ASSUMPTION (§8.6), never an external feed. The verdict is
ADVISORY; the human signs off. All math is Python Decimal — no LLM touches the numbers.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from app.core.config import settings
from app.schemas.commitment import CommitmentVerdict, ProposedDeal, StressScenario

logger = logging.getLogger("agent.commitment")

_CENTS = Decimal("0.01")


class CommitmentControlAgent:
    SCENARIO_MOVES = settings.commitment_scenario_moves  # (5, 10, 15)

    def stress_test(self, deal: ProposedDeal) -> CommitmentVerdict:
        # 1) Baseline indexed exposure (first-party assumption).
        indexed_exposure = deal.acv * deal.indexed_share * (Decimal("1") + deal.assumed_index_pct)

        # 2) Adverse-move scenarios at ±5/10/15%.
        scenarios: list[StressScenario] = []
        for m in self.SCENARIO_MOVES:
            exposure = indexed_exposure * (Decimal("1") + Decimal(m) / Decimal("100"))
            scenarios.append(
                StressScenario(
                    move_pct=m,
                    exposure=exposure.quantize(_CENTS),
                    over_tolerance=(exposure - deal.margin_tolerance) > 0,
                )
            )

        # 3) Verdict against the configurable margin tolerance.
        verdict, conditions = self._evaluate(scenarios, deal.margin_tolerance)

        return CommitmentVerdict(
            indexed_exposure=indexed_exposure.quantize(_CENTS),
            scenarios=scenarios,
            verdict=verdict,
            conditions=conditions,
            advisory=True,
        )

    def _evaluate(
        self, scenarios: list[StressScenario], tolerance: Decimal
    ) -> tuple[str, list[str]]:
        """approve  : no scenario breaches tolerance
        condition: only the worst (15%) scenario breaches → approve with conditions
        block    : a moderate scenario (≤10%) already breaches tolerance"""
        s5 = next(s for s in scenarios if s.move_pct == 5)
        s10 = next(s for s in scenarios if s.move_pct == 10)
        s15 = next(s for s in scenarios if s.move_pct == 15)

        if not s15.over_tolerance:
            return "approve", []
        if s15.over_tolerance and not s10.over_tolerance:
            shortfall = (s15.exposure - tolerance).quantize(_CENTS)
            return "condition", [
                f"Cap indexed share or negotiate an index ceiling; 15% adverse move "
                f"exceeds margin tolerance by ${shortfall}.",
                "Add an index-cap / renegotiation clause before signature.",
            ]
        # s10 (or s5) already breaches → block
        return "block", [
            f"A {'5' if s5.over_tolerance else '10'}% adverse index move already "
            f"exceeds margin tolerance — exposure is structurally unacceptable.",
        ]


commitment_control_agent = CommitmentControlAgent()


# ── advisory rationale (LLM narrative ONLY; never alters the numbers) ──────────────
async def write_commitment_rationale(
    verdict: CommitmentVerdict, deal: ProposedDeal, tenant_id: str
) -> str:
    """Plain-language narrative grounded in the FIXED Python-computed figures. Offline-safe:
    if the model gateway is unavailable (no key / provider down), return a deterministic
    summary so the verdict is never blocked on the AI layer (§15.1 graceful degradation)."""
    prompt = f"""Explain this pre-signature commitment stress test in plain language for a
finance leader. The numbers below are FIXED and Python-computed — restate them but never
recompute or alter them. Do NOT use any external/market data.

Verdict: {verdict.verdict}
Baseline indexed exposure: {verdict.indexed_exposure}
Scenarios: {[s.model_dump() for s in verdict.scenarios]}
Margin tolerance: {deal.margin_tolerance}
Conditions: {verdict.conditions}
"""
    try:
        from app.core.model_gateway import model_gateway

        result = await model_gateway.complete(
            "complex", prompt, tenant_id=tenant_id, purpose="commitment_rationale"
        )
        return result.text
    except Exception as exc:  # noqa: BLE001 — degrade gracefully, never block the verdict
        logger.warning("commitment.rationale_degraded err=%s", exc)
        return _deterministic_rationale(verdict, deal)


def _deterministic_rationale(verdict: CommitmentVerdict, deal: ProposedDeal) -> str:
    worst = max(verdict.scenarios, key=lambda s: s.exposure)
    head = {
        "approve": "Within tolerance across all modeled adverse index moves.",
        "condition": "Acceptable only with conditions — the worst-case move breaches tolerance.",
        "block": "Exposure is structurally unacceptable at a moderate adverse move.",
    }[verdict.verdict]
    return (
        f"{head} At the assumed {deal.assumed_index_pct} index, baseline indexed exposure is "
        f"${verdict.indexed_exposure}; the 15% adverse move reaches ${worst.exposure} against a "
        f"${deal.margin_tolerance} margin tolerance. (First-party assumption; advisory — the "
        f"human signs.)"
    )
