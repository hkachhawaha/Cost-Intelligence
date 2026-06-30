"""Unit tests for the 8 detection rules + scoring + the eval harness (no DB)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services.rules._types import RuleFinding
from app.services.rules.auto_renewal import detect_silent_auto_renewal
from app.services.rules.duplicate_invoice import detect_duplicate_invoices
from app.services.rules.maverick import detect_maverick
from app.services.rules.overspend import detect_overspend
from app.services.rules.unused_commitment import detect_unused_commitment
from app.services.rules.uplift_creep import detect_uplift_creep
from app.services.scoring import ScoringService

CID = uuid4()


def test_maverick_exposure_times_recapture():
    out = detect_maverick([{"spend_id": "s", "amount": "100000"}], Decimal("0.15"))
    assert out[0].impact == Decimal("15000.00")
    assert out[0].bucket == "savings" and out[0].confidence == Decimal("0.500")


def test_maverick_empty_queue_none():
    assert detect_maverick([]) == []


def test_unused_commitment_and_threshold():
    c = {"id": CID, "yearly_commit": "1000000"}
    f = detect_unused_commitment(c, Decimal("700000"), Decimal("1.0"))
    assert f and f.impact == Decimal("300000.00")
    # fully used → None
    assert detect_unused_commitment(c, Decimal("1000000"), Decimal("1.0")) is None


def test_overspend_minus_acv_and_recovery_item():
    c = {"id": CID, "acv": "1000000"}
    f = detect_overspend(c, Decimal("1200000"), Decimal("0.9"), ["s1"])
    assert f and f.impact == Decimal("200000.00")
    assert f.bucket == "recovery" and f.recovery_items[0]["amount"] == "200000.00"
    # within tolerance → None
    assert detect_overspend(c, Decimal("1010000"), Decimal("0.9"), ["s1"]) is None


def test_auto_renewal_in_window_and_uplift_creep():
    c = {
        "id": CID,
        "acv": "1000000",
        "uplift_pct": "0.07",
        "renewal_type": "auto",
        "renewal_notice_days": 30,
        "end_date": date(2026, 6, 30),
    }
    f = detect_silent_auto_renewal(c, date(2026, 6, 30))
    assert f and f.impact == Decimal("70000.00") and f.confidence == Decimal("1.000")
    # before the notice window → None
    assert detect_silent_auto_renewal(c, date(2026, 1, 1)) is None
    # uplift creep fires independently
    assert detect_uplift_creep(c).impact == Decimal("70000.00")


def test_duplicate_invoice_amount_times_occurrences():
    invs = [
        {
            "id": "i1",
            "vendor_id": "v",
            "invoice_number": "INV-1",
            "total_amount": "10000",
            "status": "paid",
        },
        {
            "id": "i2",
            "vendor_id": "v",
            "invoice_number": "INV-1",
            "total_amount": "10000",
            "status": "paid",
        },
        {
            "id": "i3",
            "vendor_id": "v",
            "invoice_number": "INV-1",
            "total_amount": "10000",
            "status": "paid",
        },
    ]
    out = detect_duplicate_invoices(invs)
    assert len(out) == 1 and out[0].impact == Decimal("20000.00")  # 10000 × (3-1)


def test_scoring_ranks_by_impact_times_confidence():
    a = RuleFinding("overspend", "recovery", Decimal("100"), Decimal("1.0"), CID)
    b = RuleFinding("maverick", "savings", Decimal("1000"), Decimal("0.5"), None)  # 500
    c = RuleFinding("uplift_creep", "savings", Decimal("100"), Decimal("0.9"), CID)  # 90
    ranked = ScoringService().rank([a, c, b])
    assert [f.type for f in ranked] == ["maverick", "overspend", "uplift_creep"]


def test_eval_harness_reproduces_241k():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from evals.detection import eval_harness

    result = eval_harness.run()
    assert result.passes(), f"grand_total={result.grand_total} by_type={result.by_type}"
