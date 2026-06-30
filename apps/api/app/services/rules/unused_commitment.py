"""Unused commitment — committed volume not consumed.
Appendix A: yearly_commit − actual matched spend (if > threshold)."""

from __future__ import annotations

from decimal import Decimal

from app.services.rules._types import RuleFinding

DEFAULT_THRESHOLD = Decimal("0.05")  # 5% of commitment; below this, ignore noise


def detect_unused_commitment(
    contract: dict,
    matched_spend_total: Decimal,
    match_confidence: Decimal,
    threshold_pct: Decimal = DEFAULT_THRESHOLD,
) -> RuleFinding | None:
    commit = _dec(contract.get("yearly_commit"))
    if commit is None or commit <= 0:
        return None
    unused = commit - matched_spend_total
    if unused <= 0 or unused < (commit * threshold_pct):
        return None
    return RuleFinding(
        type="unused_commitment",
        bucket="savings",
        impact=unused.quantize(Decimal("0.01")),
        confidence=match_confidence,
        contract_id=contract["id"],
        time_sensitivity=40,
        effort=40,
        evidence={
            "formula": "yearly_commit − Σ matched_spend",
            "yearly_commit": str(commit),
            "matched_spend": str(matched_spend_total),
            "unused": str(unused.quantize(Decimal("0.01"))),
            "threshold_pct": str(threshold_pct),
        },
    )


def _dec(v) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None
