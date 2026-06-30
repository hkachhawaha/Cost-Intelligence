"""Phase 8 unit tests (§14.1–14.3) — pure Python, no DB/LLM.

Covers the line-item recovery rules (above_rate, volume_tier) and the coexistence guard:
positive, negative, and edge scenarios. All dollar figures are computed in Python.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.invoice import Invoice, InvoiceLineItem
from app.models.opportunity import Opportunity
from app.models.rate_card import ContractRateCard, RateCardTier
from app.services.coexistence import reconcile
from app.services.rules.above_rate import detect_above_rate
from app.services.rules.volume_tier import detect_volume_tier

MC = Decimal("0.80")  # match confidence


def _invoice():
    return Invoice(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        vendor_id=uuid.uuid4(),
        invoice_number="INV-1",
    )


def _line(sku, unit_price, qty):
    return InvoiceLineItem(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        invoice_id=uuid.uuid4(),
        sku=sku,
        unit_price=unit_price,
        quantity=qty,
    )


def _card(sku, unit_rate, *, tiered=False, tiers=None):
    return ContractRateCard(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        sku=sku,
        unit_rate=Decimal(str(unit_rate)),
        is_tiered=tiered,
        tiers=tiers or [],
    )


def _tier(idx, lo, hi, rate):
    return RateCardTier(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        rate_card_id=uuid.uuid4(),
        tier_index=idx,
        min_volume=Decimal(str(lo)),
        max_volume=Decimal(str(hi)) if hi is not None else None,
        tier_rate=Decimal(str(rate)),
    )


# ── above_rate ────────────────────────────────────────────────────────────────
def test_above_rate_basic():
    inv = _invoice()
    li = _line("CLOUD", Decimal("0.048"), Decimal("250000"))
    opp = detect_above_rate(inv, [li], {"CLOUD": _card("CLOUD", "0.042")}, MC)
    assert opp is not None and opp.type == "above_rate" and opp.bucket == "recovery"
    assert opp.impact == Decimal("1500.000")  # (0.048-0.042)*250000
    assert opp.confidence == MC  # inherits match confidence


def test_above_rate_no_overcharge():
    inv = _invoice()
    li = _line("CLOUD", Decimal("0.042"), Decimal("1000"))
    assert detect_above_rate(inv, [li], {"CLOUD": _card("CLOUD", "0.042")}, MC) is None


def test_above_rate_no_rate_card_advisory():
    # SKU absent from cards → advisory, never a $ finding, excluded from totals.
    inv = _invoice()
    li = _line("NOCARD", Decimal("9.99"), Decimal("10"))
    opp = detect_above_rate(inv, [li], {}, MC)
    assert opp is not None and opp.status == "requires_rate_card_data"
    assert opp.impact == Decimal("0") and opp.counts_in_total is False


def test_above_rate_null_qty_skipped():
    inv = _invoice()
    li = _line("CLOUD", Decimal("0.048"), None)  # missing qty → skipped, no exception
    assert detect_above_rate(inv, [li], {"CLOUD": _card("CLOUD", "0.042")}, MC) is None


# ── volume_tier ─────────────────────────────────────────────────────────────
def _tiered_card(sku):
    return _card(
        sku,
        "0",
        tiered=True,
        tiers=[
            _tier(0, 0, 100, 120),
            _tier(1, 100, 500, 100),
            _tier(2, 500, None, 85),
        ],
    )


def test_tier_qualifies_cheaper():
    # Total volume 600 qualifies tier-2 (85); the single 600-qty line was billed tier-2...
    # so to show recovery, bill it at tier-1 by splitting? Use one line of 600 billed where
    # the per-line band would be tier-2 — instead use volume that bills higher tier per line.
    card = _tiered_card("SEATS")
    # One line of qty 300 (per-line band → tier-1 @100); total period volume 600 → tier-2 @85.
    li = _line("SEATS", Decimal("100"), Decimal("300"))
    li2 = _line("SEATS", Decimal("100"), Decimal("300"))
    opps = detect_volume_tier(uuid.uuid4(), uuid.uuid4(), [li, li2], {"SEATS": card}, MC)
    assert len(opps) == 1
    # Each line: (100-85)*300 = 4500; two lines → 9000.
    assert opps[0].impact == Decimal("9000")


def test_tier_already_at_best():
    card = _tiered_card("SEATS")
    # Single line qty 600 → per-line band tier-2 (85); total 600 → tier-2 → no recovery.
    li = _line("SEATS", Decimal("85"), Decimal("600"))
    assert detect_volume_tier(uuid.uuid4(), uuid.uuid4(), [li], {"SEATS": card}, MC) == []


def test_tier_below_floor_no_exception():
    # Volume below the lowest tier floor uses the lowest tier rate (no exception).
    card = _card("X", "0", tiered=True, tiers=[_tier(0, 10, 100, 50), _tier(1, 100, None, 40)])
    li = _line("X", Decimal("50"), Decimal("5"))  # below floor (10)
    out = detect_volume_tier(uuid.uuid4(), uuid.uuid4(), [li], {"X": card}, MC)
    assert out == []  # billed idx == qualified idx (both lowest) → no recovery, no error


# ── coexistence ──────────────────────────────────────────────────────────────
def test_coexistence_demotes_header_when_line_covers():
    cid = uuid.uuid4()
    header = Opportunity(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        contract_id=cid,
        type="overspend",
        bucket="recovery",
        impact=Decimal("5000"),
        confidence=MC,
        status="detected",
        granularity="header",
        counts_in_total=True,  # DB default not applied to transient objects
    )
    line = Opportunity(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        contract_id=cid,
        type="above_rate",
        bucket="recovery",
        impact=Decimal("1500"),
        confidence=MC,
        status="detected",
        granularity="line_item",
    )
    reconcile([header, line])
    assert header.counts_in_total is False  # demoted (line-item view counts)
    assert header.superseded_by_id == line.id and line.supersedes_id == header.id


def test_coexistence_no_demotion_without_overlap():
    cid = uuid.uuid4()
    header = Opportunity(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        contract_id=cid,
        type="duplicate_invoice",
        bucket="recovery",
        impact=Decimal("800"),
        confidence=MC,
        status="detected",
        granularity="header",
        counts_in_total=True,  # DB default not applied to transient objects
    )
    line = Opportunity(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        contract_id=cid,
        type="above_rate",
        bucket="recovery",
        impact=Decimal("1500"),
        confidence=MC,
        status="detected",
        granularity="line_item",
    )
    reconcile([header, line])
    assert header.counts_in_total is True  # no overlap → both count
