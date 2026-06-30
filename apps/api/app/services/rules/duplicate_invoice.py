"""Duplicate invoice — same invoice paid more than once.
Appendix A: invoice amount × (occurrences − 1). Recovery bucket."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.services.rules._types import RuleFinding


def detect_duplicate_invoices(invoices: list[dict]) -> list[RuleFinding]:
    """Group paid invoices by (vendor_id, invoice_number, total_amount). A group
    of size n>1 means (n−1) duplicate payments of `amount`. Same number with a
    different amount is treated as a revision (separate group), not a duplicate."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for inv in invoices:
        if inv.get("status") != "paid":
            continue
        key = (str(inv["vendor_id"]), inv["invoice_number"], str(inv["total_amount"]))
        groups[key].append(inv)

    findings: list[RuleFinding] = []
    for (_vendor_id, number, amount_str), dupes in groups.items():
        if len(dupes) <= 1:
            continue
        amount = Decimal(amount_str)
        impact = (amount * (len(dupes) - 1)).quantize(Decimal("0.01"))
        invoice_ids = [str(d["id"]) for d in dupes]
        contract_id = dupes[0].get("contract_id")
        findings.append(
            RuleFinding(
                type="duplicate_invoice",
                bucket="recovery",
                impact=impact,
                confidence=Decimal("1.000"),
                contract_id=contract_id,
                time_sensitivity=70,
                effort=20,
                evidence={
                    "formula": "invoice_amount × (occurrences − 1)",
                    "invoice_number": number,
                    "amount": amount_str,
                    "occurrences": len(dupes),
                    "invoice_ids": invoice_ids,
                },
                recovery_items=[
                    {
                        "amount": str(impact),
                        "evidence": {"invoice_number": number, "invoice_ids": invoice_ids},
                    }
                ],
            )
        )
    return findings
