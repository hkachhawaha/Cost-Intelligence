"""Spend after expiry — spend dated after the contract end date.
Appendix A: Σ spend where spend_date > end_date. Recovery bucket."""

from __future__ import annotations

from decimal import Decimal

from app.services.rules._types import RuleFinding


def detect_post_expiry(
    contract: dict, matched_spend: list[dict], match_confidence: Decimal
) -> RuleFinding | None:
    end_date = contract.get("end_date")
    if end_date is None:
        return None
    after = [s for s in matched_spend if s["spend_date"] > end_date]
    if not after:
        return None
    total = sum((Decimal(str(s["amount"])) for s in after), Decimal("0"))
    if total <= 0:
        return None
    total = total.quantize(Decimal("0.01"))
    spend_ids = [str(s["spend_id"]) for s in after]
    return RuleFinding(
        type="post_expiry",
        bucket="recovery",
        impact=total,
        confidence=match_confidence,
        contract_id=contract["id"],
        time_sensitivity=55,
        effort=45,
        evidence={
            "formula": "Σ spend where spend_date > end_date",
            "end_date": end_date.isoformat(),
            "post_expiry_total": str(total),
            "post_expiry_count": len(after),
            "spend_ids": spend_ids[:500],
        },
        recovery_items=[
            {
                "amount": str(total),
                "evidence": {"end_date": end_date.isoformat(), "spend_ids": spend_ids[:500]},
            }
        ],
    )
