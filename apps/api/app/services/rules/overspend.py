"""Overspend vs ACV — matched spend exceeds annual contract value.
Appendix A: actual matched spend − ACV (if positive). Recovery bucket."""

from __future__ import annotations

from decimal import Decimal

from app.services.rules._types import RuleFinding

DEFAULT_TOLERANCE = Decimal("0.02")  # 2% tolerance band before flagging


def detect_overspend(
    contract: dict,
    matched_spend_total: Decimal,
    match_confidence: Decimal,
    matched_spend_ids: list[str],
    tolerance_pct: Decimal = DEFAULT_TOLERANCE,
) -> RuleFinding | None:
    acv = _dec(contract.get("acv"))
    if acv is None or acv <= 0:
        return None
    overspend = matched_spend_total - acv
    if overspend <= (acv * tolerance_pct):
        return None
    overspend = overspend.quantize(Decimal("0.01"))
    return RuleFinding(
        type="overspend",
        bucket="recovery",
        impact=overspend,
        confidence=match_confidence,
        contract_id=contract["id"],
        time_sensitivity=30,
        effort=50,
        evidence={
            "formula": "Σ matched_spend − ACV",
            "acv": str(acv),
            "matched_spend": str(matched_spend_total),
            "overspend": str(overspend),
            "tolerance_pct": str(tolerance_pct),
            "spend_ids": matched_spend_ids[:500],
        },
        recovery_items=[
            {
                "amount": str(overspend),
                "evidence": {"acv": str(acv), "spend_ids": matched_spend_ids[:500]},
            }
        ],
    )


def _dec(v) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None
