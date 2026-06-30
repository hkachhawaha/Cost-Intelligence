"""Unit tests for the deterministic matching core (no DB, no LLM)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.matching import (
    FUZZY_FLOOR,
    REVIEW_THRESHOLD,
    SPOT_CHECK_THRESHOLD,
    W_AMOUNT,
    W_COST_CENTER,
    W_DATE,
    W_VENDOR,
    MatchingService,
)


def _svc() -> MatchingService:
    return MatchingService(session=None, candidates=None)  # type: ignore[arg-type]


def _spend(**kw):
    base = dict(
        id=uuid4(),
        tenant_id=uuid4(),
        vendor_id="v1",
        amount=Decimal("10000"),
        spend_date=date(2026, 3, 1),
        po_number=None,
        cost_center=None,
        invoice_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _contract(**kw):
    base = dict(
        id=uuid4(),
        vendor_id="v1",
        acv=Decimal("120000"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        po_numbers=[],
        entity_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_po_exact_confidence_one_and_case_insensitive():
    svc = _svc()
    spend = _spend(po_number="po-1")
    contract = _contract(po_numbers=["PO-1"])
    result = svc.match_by_po(spend, [contract])
    assert result is not None
    assert result.method == "po_exact"
    assert result.confidence == Decimal("1.000")


def test_amount_similarity_exact_monthly_and_null_acv():
    svc = _svc()
    assert svc._amount_similarity(Decimal("10000"), Decimal("120000")) == Decimal(
        "1.0"
    )  # 120000/12
    assert svc._amount_similarity(Decimal("10000"), None) == Decimal("0.0")


def test_date_proximity_in_term_and_beyond_window():
    svc = _svc()
    start, end = date(2026, 1, 1), date(2026, 1, 31)
    assert svc._date_proximity(date(2026, 1, 15), start, end) == Decimal("1.0")
    assert svc._date_proximity(date(2026, 4, 1), start, end) == Decimal("0.0")  # >45d past end


def test_fuzzy_weights_sum_to_one():
    assert W_VENDOR + W_AMOUNT + W_DATE + W_COST_CENTER == Decimal("1.0")


def test_classify_bands():
    svc = _svc()
    assert svc._classify(Decimal("1.0")) == "accepted"
    assert svc._classify(SPOT_CHECK_THRESHOLD - Decimal("0.01")) == "spot_check"
    assert svc._classify(REVIEW_THRESHOLD - Decimal("0.01")) == "needs_review"
    assert svc._classify(FUZZY_FLOOR - Decimal("0.01")) == "unmatched"


def test_fuzzy_below_floor_returns_none():
    svc = _svc()
    # Different vendor + amount far off + date out of term ⇒ score below 0.50 floor.
    spend = _spend(vendor_id="other", amount=Decimal("999999"), spend_date=date(2030, 1, 1))
    contract = _contract(vendor_id="v1")
    assert svc.match_by_vendor_amount_date(spend, [contract]) is None


def test_eval_harness_meets_gate():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from evals.matching import eval_harness

    result = eval_harness.run(_svc())
    assert result.passes(), (
        f"precision={result.precision} recall={result.recall} coverage={result.coverage_pct}"
    )
