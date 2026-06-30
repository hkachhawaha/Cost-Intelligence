"""Volume-tier detection (v1.5, Recovery bucket) — §5.2.

The customer's ACTUAL aggregated purchase volume for a SKU over the contract period may
qualify for a cheaper tier than the one billed.

Impact = Σ over line items of (billed_tier_rate − qualified_tier_rate) × quantity
  where  billed_tier_rate    = tier whose band contains the per-line volume,
         qualified_tier_rate = tier whose band contains the TOTAL period volume.

All math in Python; the LLM never computes this figure.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.models.invoice import InvoiceLineItem
from app.models.opportunity import Opportunity
from app.models.rate_card import ContractRateCard, RateCardTier


def _rate_for_volume(tiers: list[RateCardTier], volume: Decimal) -> tuple[Decimal, int]:
    """(tier_rate, tier_index) for the tier whose band [min, max) contains `volume`.
    Top tier (max_volume None) is open-ended; below the floor → lowest tier."""
    for t in sorted(tiers, key=lambda x: x.tier_index):
        if volume >= t.min_volume and (t.max_volume is None or volume < t.max_volume):
            return t.tier_rate, t.tier_index
    lowest = min(tiers, key=lambda x: x.tier_index)
    return lowest.tier_rate, lowest.tier_index


def detect_volume_tier(
    tenant_id,
    contract_id,
    line_items: list[InvoiceLineItem],
    tiered_cards: dict[str, ContractRateCard],  # canonical_sku -> tiered rate card
    match_confidence: Decimal,
) -> list[Opportunity]:
    """One Opportunity per SKU whose total period volume qualifies for a cheaper tier."""
    total_volume: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    sku_lines: dict[str, list[InvoiceLineItem]] = defaultdict(list)
    for li in line_items:
        if li.sku in tiered_cards and li.quantity is not None:
            total_volume[li.sku] += li.quantity
            sku_lines[li.sku].append(li)

    opportunities: list[Opportunity] = []
    for sku, lines in sku_lines.items():
        card = tiered_cards[sku]
        qualified_rate, qualified_idx = _rate_for_volume(card.tiers, total_volume[sku])

        savings = Decimal("0")
        line_evidence = []
        for li in lines:
            if li.quantity is None:
                continue
            billed_rate, billed_idx = _rate_for_volume(card.tiers, li.quantity)
            # Higher tier_index = cheaper rate. Recovery exists only when the line was
            # billed at a MORE-expensive (lower-index) tier than the aggregate volume
            # qualifies for. Skip when already at/below (i.e. index >=) the qualified tier.
            if billed_idx >= qualified_idx:
                continue
            line_saving = (billed_rate - qualified_rate) * li.quantity
            savings += line_saving
            line_evidence.append(
                {
                    "line_item_id": str(li.id),
                    "sku": sku,
                    "quantity": str(li.quantity),
                    "billed_tier_index": billed_idx,
                    "billed_rate": str(billed_rate),
                    "qualified_tier_index": qualified_idx,
                    "qualified_rate": str(qualified_rate),
                    "line_saving": str(line_saving),
                }
            )

        if savings > 0:
            opportunities.append(
                Opportunity(
                    tenant_id=tenant_id,
                    contract_id=contract_id,
                    type="volume_tier",
                    bucket="recovery",
                    granularity="line_item",
                    impact=savings,
                    confidence=match_confidence,
                    status="detected",
                    evidence={
                        "formula": "Σ (billed_tier_rate − qualified_tier_rate) × quantity",
                        "sku": sku,
                        "total_period_volume": str(total_volume[sku]),
                        "qualified_tier_index": qualified_idx,
                        "qualified_rate": str(qualified_rate),
                        "lines": line_evidence,
                    },
                )
            )
    return opportunities
