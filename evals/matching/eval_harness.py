"""Matching eval harness — precision / recall / coverage against a golden set.

Runs the deterministic MatchingService tiers (PO + fuzzy; no LLM) over labeled
spend↔contract pairs and gates CI: precision ≥ 0.90, recall ≥ 0.85,
coverage ≥ 94.9% (prototype parity, §1/§13).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

GOLDEN = Path(__file__).parent / "golden" / "golden_pairs.jsonl"


@dataclass
class EvalResult:
    precision: float
    recall: float
    coverage_pct: float
    auto_match_count: int
    false_positive_count: int

    def passes(self) -> bool:
        return self.precision >= 0.90 and self.recall >= 0.85 and self.coverage_pct >= 94.9


def _to_spend(row: dict):
    return SimpleNamespace(
        id=row["spend_id"], tenant_id=uuid4(), vendor_id=row["vendor_id"],
        amount=Decimal(str(row["amount"])), spend_date=date.fromisoformat(row["spend_date"]),
        po_number=row.get("po_number"), cost_center=row.get("cost_center"), invoice_id=None,
    )


def _to_contracts(rows: list[dict]):
    return [
        SimpleNamespace(
            id=c["id"], vendor_id=c["vendor_id"],
            acv=Decimal(str(c["acv"])) if c.get("acv") else None,
            start_date=date.fromisoformat(c["start_date"]),
            end_date=date.fromisoformat(c["end_date"]),
            po_numbers=c.get("po_numbers", []), entity_id=None,
        )
        for c in rows
    ]


def run(svc) -> EvalResult:
    """`svc` is a MatchingService (only its pure tier methods are used)."""
    golden = [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]
    tp = fp = fn = matched = total = 0
    for row in golden:
        total += 1
        spend = _to_spend(row)
        candidates = _to_contracts(row["candidates"])
        result = svc.match_by_po(spend, candidates) or svc.match_by_vendor_amount_date(
            spend, candidates
        )
        predicted = str(result.contract_id) if result and result.contract_id else None
        expected = row["expected_contract_id"]
        if predicted is not None:
            matched += 1
            tp += 1 if predicted == expected else 0
            fp += 0 if predicted == expected else 1
        if expected is not None and predicted != expected:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    coverage = matched / total * 100 if total else 0.0
    return EvalResult(precision, recall, coverage, matched, fp)
