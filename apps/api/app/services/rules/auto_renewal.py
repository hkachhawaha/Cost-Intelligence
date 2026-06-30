"""Silent auto-renewal — auto-renew contract inside its notice window.
Appendix A: ACV × uplift% (negotiable); next-term value = ACV × (1+uplift)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.services.rules._types import RuleFinding


def detect_silent_auto_renewal(contract: dict, today: date) -> RuleFinding | None:
    if contract.get("renewal_type") != "auto":
        return None
    end_date = contract["end_date"]
    if end_date is None:
        return None
    notice_days = int(contract.get("renewal_notice_days") or 0)
    notice_deadline = end_date - timedelta(days=notice_days)
    if today < notice_deadline:
        return None

    acv = Decimal(str(contract["acv"])) if contract.get("acv") is not None else Decimal("0")
    uplift = Decimal(str(contract.get("uplift_pct") or "0"))
    negotiable = (acv * uplift).quantize(Decimal("0.01"))
    next_term_value = (acv * (Decimal("1") + uplift)).quantize(Decimal("0.01"))
    days_to_deadline = max(0, (notice_deadline - today).days)
    time_sensitivity = 100 if days_to_deadline == 0 else max(0, 100 - days_to_deadline)

    return RuleFinding(
        type="auto_renewal",
        bucket="savings",
        impact=negotiable,
        confidence=Decimal("1.000"),
        contract_id=contract["id"],
        time_sensitivity=time_sensitivity,
        effort=30,
        evidence={
            "formula": "ACV × uplift_pct",
            "acv": str(acv),
            "uplift_pct": str(uplift),
            "next_term_value": str(next_term_value),
            "notice_deadline": notice_deadline.isoformat(),
            "days_to_deadline": days_to_deadline,
        },
    )
