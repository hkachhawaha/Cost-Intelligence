"""Uplift creep — any positive renewal uplift, quantified.
Appendix A: ACV × uplift%."""

from __future__ import annotations

from decimal import Decimal

from app.services.rules._types import RuleFinding


def detect_uplift_creep(contract: dict) -> RuleFinding | None:
    uplift = Decimal(str(contract.get("uplift_pct") or "0"))
    if uplift <= 0:
        return None
    acv = Decimal(str(contract["acv"])) if contract.get("acv") is not None else Decimal("0")
    creep = (acv * uplift).quantize(Decimal("0.01"))
    if creep <= 0:
        return None
    return RuleFinding(
        type="uplift_creep",
        bucket="savings",
        impact=creep,
        confidence=Decimal("1.000"),
        contract_id=contract["id"],
        time_sensitivity=25,
        effort=35,
        evidence={
            "formula": "ACV × uplift_pct",
            "acv": str(acv),
            "uplift_pct": str(uplift),
            "creep_amount": str(creep),
        },
    )
