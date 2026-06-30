"""Detection eval harness — reproduces ~$241K on the synthetic dataset.

Runs the 8 pure rule functions (via DetectionService.run_rules_over) over an
in-memory reconciled fixture and asserts the grand total (savings + recovery) is
within ±3% of the prototype's $241K, with a per-type breakdown so a
compensating-error bug can't pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.services.detection import DetectionService
from app.services.scoring import ScoringService

GOLDEN = Path(__file__).parent / "golden" / "synthetic_dataset.json"


@dataclass
class DetectionEvalResult:
    grand_total: Decimal
    savings_total: Decimal
    recovery_total: Decimal
    by_type: dict = field(default_factory=dict)
    expected_total: Decimal = Decimal("241000")
    tolerance: Decimal = Decimal("0.03")

    def passes(self) -> bool:
        lo = self.expected_total * (Decimal("1") - self.tolerance)
        hi = self.expected_total * (Decimal("1") + self.tolerance)
        return lo <= self.grand_total <= hi


def _to_data(raw: dict) -> dict:
    """Convert the JSON fixture into the in-memory reconciled `data` dict, parsing
    dates (rules do date arithmetic) — amounts stay strings (rules wrap in Decimal)."""
    contracts = []
    for c in raw["contracts"]:
        c = dict(c)
        c["end_date"] = date.fromisoformat(c["end_date"]) if c.get("end_date") else None
        contracts.append(c)
    matched = {
        cid: [{**s, "spend_date": date.fromisoformat(s["spend_date"])} for s in rows]
        for cid, rows in raw["matched_by_contract"].items()
    }
    confidence = {cid: Decimal(str(v)) for cid, v in raw["confidence_by_contract"].items()}
    return {
        "contracts": contracts,
        "matched_by_contract": matched,
        "confidence_by_contract": confidence,
        "unmatched_spend": raw["unmatched_spend"],
        "invoices": raw["invoices"],
        "invoice_pos_by_contract": {k: set(v) for k, v in raw["invoice_pos_by_contract"].items()},
    }


def run() -> DetectionEvalResult:
    raw = json.loads(GOLDEN.read_text())
    data = _to_data(raw)
    svc = DetectionService(session=None, scoring=ScoringService())  # type: ignore[arg-type]
    findings = svc.run_rules_over(data, date.fromisoformat(raw["as_of"]))

    savings = sum((f.impact for f in findings if f.bucket == "savings"), Decimal("0"))
    recovery = sum((f.impact for f in findings if f.bucket == "recovery"), Decimal("0"))
    by_type: dict[str, str] = {}
    for f in findings:
        by_type[f.type] = str(Decimal(by_type.get(f.type, "0")) + f.impact)
    return DetectionEvalResult(
        grand_total=savings + recovery, savings_total=savings,
        recovery_total=recovery, by_type=by_type,
    )
