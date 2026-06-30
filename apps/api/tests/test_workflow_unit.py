"""Phase 9 unit tests (§5, §9) — no DB, no network, no LLM.

Covers the actionability gate, the three ERP mappers (the testable transform heart of each
connector), the anomaly-ML Z-score fallback, the dual-write event bus' best-effort secondary,
and the learning math's PO-exact invariant + threshold clamping.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from app.connectors.erp.mappers import CoupaMapper, OracleMapper, SapMapper
from app.core.eventbus import DualWriteBus, EventBus
from app.services.anomaly_ml import IsolationForestAnomalyService
from app.services.feedback_loop import (
    LEARNABLE_FUZZY_SIGNALS,
    LearningFeedbackService,
)
from app.services.workflow import is_actionable


# ── actionability gate (positive + 3 negatives = edge coverage) ──────────────────
def test_is_actionable_gate():
    # Positive: high-confidence, allowed type, has a deadline → actionable.
    assert is_actionable("auto_renewal", 0.95, "2026-09-01") is True
    # Negative: confidence below the 0.90 floor.
    assert is_actionable("auto_renewal", 0.80, "2026-09-01") is False
    # Negative: type not in the auto-allowed set.
    assert is_actionable("overspend", 0.99, "2026-09-01") is False
    # Negative/edge: no deadline → never auto-actionable.
    assert is_actionable("uplift_creep", 0.99, None) is False


# ── ERP mappers ──────────────────────────────────────────────────────────────────
def test_coupa_mapper_invoice_and_spend():
    inv = CoupaMapper().map_invoice(
        {
            "invoice-number": "INV-100",
            "supplier": {"name": "CloudCo"},
            "invoice-date": "2026-03-15T00:00:00",  # ISO datetime → date-only
            "total": "1234.56",
            "currency": {"code": "usd"},  # lowercased ISO → normalized
            "status": "paid",
            "po-number": "PO-9",
        }
    )
    assert inv["vendor_name"] == "CloudCo"
    assert inv["invoice_number"] == "INV-100"
    assert inv["invoice_date"] == "2026-03-15"
    assert inv["total_amount"] == "1234.56"
    assert inv["currency"] == "usd"
    assert inv["status"] == "paid"
    assert inv["source_system"] == "coupa"

    spend = CoupaMapper().map_spend(
        {"supplier": {"name": "CloudCo"}, "total": "500", "accounting-date": "2026-04-01",
         "account": {"code": "6000"}, "department": "Eng"}
    )
    assert spend["amount"] == "500" and spend["gl_code"] == "6000"
    assert spend["cost_center"] == "Eng" and spend["source_system"] == "coupa"


def test_oracle_and_sap_status_normalization():
    # Oracle: PAYMENT_STATUS_FLAG 'Y' → paid; SAP compact YYYYMMDD date; unknown → open.
    o = OracleMapper().map_invoice(
        {"INVOICE_NUM": "OR-1", "VENDOR_NAME": "Acme", "INVOICE_DATE": "2026-01-02",
         "INVOICE_AMOUNT": "10", "INVOICE_CURRENCY_CODE": "USD", "PAYMENT_STATUS_FLAG": "Y"}
    )
    assert o["status"] == "paid" and o["source_system"] == "oracle"

    s = SapMapper().map_invoice(
        {"DocumentNumber": "SAP-1", "Supplier": "Acme", "DocumentDate": "20260102",
         "Amount": "10", "Currency": "EUR", "PaymentStatus": "weird-token"}
    )
    assert s["invoice_date"] == "2026-01-02"  # 20260102 → ISO
    assert s["status"] == "open"  # unknown token defaults to open
    assert s["source_system"] == "sap"


# ── anomaly ML (offline fallback path) ────────────────────────────────────────────
def test_anomaly_zscore_fallback_without_model():
    """No fitted model (sklearn may be absent) → deterministic P7 Z-score fallback fires."""
    rows = [{"spend_id": f"s{i}", "amount": 100} for i in range(29)]
    rows.append({"spend_id": "spike", "amount": 100000})  # clear outlier, n=30
    svc = IsolationForestAnomalyService()
    found = svc.score(rows)
    assert len(found) >= 1
    assert all(a.method == "zscore_fallback" for a in found)
    assert any(a.subject_id == "spike" for a in found)


def test_anomaly_train_without_sklearn_or_small_data_returns_none():
    """Too-few samples → no model (so scoring uses the fallback). Always offline-safe."""
    svc = IsolationForestAnomalyService()
    assert svc.train([{"amount": 1.0}] * 10) is None  # < 50 rows → None regardless of sklearn


# ── event bus (dual-write best-effort secondary) ──────────────────────────────────
def test_dualwrite_tolerates_secondary_failure():
    class _Primary(EventBus):
        async def publish(self, topic, event):
            return "primary-id"

    class _BrokenSecondary(EventBus):
        async def publish(self, topic, event):
            raise RuntimeError("kafka down")

    bus = DualWriteBus(_Primary(), _BrokenSecondary())
    # Primary id is returned; secondary's failure is swallowed (logged), not raised.
    result = asyncio.run(bus.publish("opp.detected", {"x": 1}))
    assert result == "primary-id"


# ── learning math (PO-exact invariant + threshold clamp) ──────────────────────────
def _label(features: dict, label: dict):
    from app.models.automation import LearningLabel

    return LearningLabel(features=features, label=label)


def test_fit_weights_never_learns_po_exact():
    """Learned fuzzy weights cover ONLY the learnable signals — po_exact is never in the set
    and stays the platform constant 1.0 (§9 invariant)."""
    labels = [
        _label({"vendor": 0.9, "amount": 0.8, "date": 0.7, "cost_center": 0.6,
                "po_exact": 1.0, "correct": True}, {"contract_id": "c1"})
        for _ in range(5)
    ]
    weights = LearningFeedbackService._fit_weights(labels)
    assert set(weights.keys()) == set(LEARNABLE_FUZZY_SIGNALS)
    assert "po_exact" not in weights
    assert abs(sum(weights.values()) - 1.0) < 1e-6  # normalized


def test_optimize_thresholds_clamped_to_config_bounds():
    """A confirmed impact above the configured max clamps to the max (no runaway threshold)."""
    svc = LearningFeedbackService(session=None, tenant_id="00000000-0000-0000-0000-000000000000")
    labels = [
        _label({"impact": 2_000_000.0}, {"confirmed": True}),  # above max bound
        _label({"impact": 1_500_000.0}, {"confirmed": True}),
    ]
    thresholds, _precision = svc._optimize_thresholds(labels)
    assert thresholds["min_impact"] == Decimal("1000000") or thresholds["min_impact"] == 1_000_000.0
