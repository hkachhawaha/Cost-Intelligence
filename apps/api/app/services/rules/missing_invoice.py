"""Missing invoice — spend/PO with no corresponding invoice. Control bucket.
Not recoverable cash; a data/control gap that weakens 3-way match."""

from __future__ import annotations

from decimal import Decimal

from app.services.rules._types import RuleFinding


def detect_missing_invoice(
    contract: dict,
    matched_spend: list[dict],
    invoice_pos: set[str],
    match_confidence: Decimal,
) -> RuleFinding | None:
    missing = [s for s in matched_spend if s.get("po_number") and s["po_number"] not in invoice_pos]
    if not missing:
        return None
    exposure = sum((Decimal(str(s["amount"])) for s in missing), Decimal("0")).quantize(
        Decimal("0.01")
    )
    spend_ids = [str(s["spend_id"]) for s in missing]
    return RuleFinding(
        type="missing_invoice",
        bucket="control",
        impact=exposure,
        confidence=match_confidence,
        contract_id=contract["id"],
        time_sensitivity=15,
        effort=40,
        evidence={
            "formula": "spend/PO with no matching invoice",
            "missing_count": len(missing),
            "exposure": str(exposure),
            "spend_ids": spend_ids[:500],
        },
    )
