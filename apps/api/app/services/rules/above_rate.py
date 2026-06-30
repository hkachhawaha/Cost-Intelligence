"""Above-rate detection (v1.5, Recovery bucket) — §5.1.

Formula:  overcharge = Σ over line items L where a contracted rate exists and
                       billed_price > contracted_rate of
                       (L.unit_price − contracted_rate) × L.quantity

Hard rules:
  * Runs ONLY where a (flat) rate card exists for the SKU. If NO rate card exists for an
    invoice's SKUs, emit a `requires_rate_card_data` advisory — NEVER a dollar finding
    (first-party integrity; no fabricated figures, §5.6).
  * All math in Python; the LLM never computes this figure.
  * Confidence inherits the underlying match confidence (line→contract).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.models.invoice import Invoice, InvoiceLineItem
from app.models.opportunity import Opportunity
from app.models.rate_card import ContractRateCard


@dataclass
class LineOvercharge:
    line_item_id: str
    sku: str
    quantity: Decimal
    billed_rate: Decimal
    contracted_rate: Decimal
    delta: Decimal  # (billed − contracted) × qty


def detect_above_rate(
    invoice: Invoice,
    line_items: list[InvoiceLineItem],
    rate_cards: dict[str, ContractRateCard],  # canonical_sku -> non-tiered rate card
    match_confidence: Decimal,
) -> Opportunity | None:
    """One Opportunity per invoice summarizing per-SKU overcharges, or None.

    `rate_cards` contains ONLY non-tiered cards for the governing contract; tiered SKUs
    are owned by `detect_volume_tier` and skipped here.
    """
    overcharges: list[LineOvercharge] = []
    skus_without_rate: set[str] = set()

    for li in line_items:
        if li.sku is None or li.unit_price is None or li.quantity is None:
            continue
        card = rate_cards.get(li.sku)
        if card is None:
            skus_without_rate.add(li.sku)
            continue
        if card.is_tiered:  # tier logic owns this SKU
            continue
        if li.unit_price > card.unit_rate:
            delta = (li.unit_price - card.unit_rate) * li.quantity
            overcharges.append(
                LineOvercharge(
                    line_item_id=str(li.id),
                    sku=li.sku,
                    quantity=li.quantity,
                    billed_rate=li.unit_price,
                    contracted_rate=card.unit_rate,
                    delta=delta,
                )
            )

    total = sum((o.delta for o in overcharges), Decimal("0"))

    # No overcharge AND every SKU had a rate card → genuinely clean, no opp.
    if total <= 0 and not skus_without_rate:
        return None

    # No overcharge but some SKUs lacked rate cards → advisory, NOT a $ finding.
    if total <= 0 and skus_without_rate:
        return Opportunity(
            tenant_id=invoice.tenant_id,
            contract_id=invoice.contract_id,
            type="above_rate",
            bucket="recovery",
            granularity="line_item",
            impact=Decimal("0"),
            confidence=match_confidence,
            status="requires_rate_card_data",  # surfaced in UI, excluded from totals
            counts_in_total=False,
            evidence={
                "advisory": "requires rate card data",
                "skus_without_rate": sorted(skus_without_rate),
                "invoice_id": str(invoice.id),
            },
        )

    return Opportunity(
        tenant_id=invoice.tenant_id,
        contract_id=invoice.contract_id,
        type="above_rate",
        bucket="recovery",
        granularity="line_item",
        impact=total,
        confidence=match_confidence,
        status="detected",
        evidence={
            "formula": "Σ (invoice_unit_price − contracted_rate) × quantity, per SKU",
            "invoice_id": str(invoice.id),
            "line_overcharges": [
                {
                    "line_item_id": o.line_item_id,
                    "sku": o.sku,
                    "quantity": str(o.quantity),
                    "billed_rate": str(o.billed_rate),
                    "contracted_rate": str(o.contracted_rate),
                    "delta": str(o.delta),
                }
                for o in overcharges
            ],
            "skus_without_rate": sorted(skus_without_rate),
        },
    )
