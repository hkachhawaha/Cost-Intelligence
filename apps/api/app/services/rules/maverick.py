"""Maverick spend — spend with no governing contract.
Appendix A: Σ unmatched spend; savings = exposure × recapture_rate (param)."""

from __future__ import annotations

from decimal import Decimal

from app.services.rules._types import RuleFinding

DEFAULT_RECAPTURE_RATE = Decimal("0.15")


def detect_maverick(
    unmatched_spend: list[dict], recapture_rate: Decimal = DEFAULT_RECAPTURE_RATE
) -> list[RuleFinding]:
    if not unmatched_spend:
        return []
    exposure = sum((Decimal(str(s["amount"])) for s in unmatched_spend), Decimal("0"))
    if exposure <= 0:
        return []
    savings = (exposure * recapture_rate).quantize(Decimal("0.01"))
    spend_ids = [str(s["spend_id"]) for s in unmatched_spend]
    by_vendor: dict[str, str] = {}
    for s in unmatched_spend:
        v = str(s.get("vendor_name", "unknown"))
        by_vendor[v] = str(Decimal(by_vendor.get(v, "0")) + Decimal(str(s["amount"])))
    return [
        RuleFinding(
            type="maverick",
            bucket="savings",
            impact=savings,
            confidence=Decimal("0.500"),
            contract_id=None,
            time_sensitivity=20,
            effort=60,
            evidence={
                "formula": "Σ unmatched_spend × recapture_rate",
                "exposure": str(exposure.quantize(Decimal("0.01"))),
                "recapture_rate": str(recapture_rate),
                "unmatched_count": len(unmatched_spend),
                "spend_ids": spend_ids[:500],
                "exposure_by_vendor": by_vendor,
            },
        )
    ]
