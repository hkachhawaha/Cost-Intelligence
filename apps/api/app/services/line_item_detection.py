"""LineItemDetectionService (§5.6) — runs the v1.5 line-item rules and reconciles them
with the v1 header findings (coexistence dedup), persisting new opportunities.

Kept separate from the Phase-3 `DetectionService.run_all_rules` so header detection is
untouched. Runs only where line items + verified rate cards exist; degrades gracefully
to `requires_rate_card_data` advisories otherwise.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceLineItem
from app.models.matching import MatchResult
from app.models.opportunity import Opportunity
from app.services.coexistence import reconcile
from app.services.rate_card import RateCardService
from app.services.rules.above_rate import detect_above_rate
from app.services.rules.volume_tier import detect_volume_tier

logger = logging.getLogger("detection.line_item")
_DEFAULT_CONFIDENCE = Decimal("0.90")


class LineItemDetectionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.rate_cards = RateCardService(session)

    async def run(self, tenant_id: str) -> list[Opportunity]:
        # The session is already RLS-bound to this tenant; tenant_id is for logging/lineage.
        logger.info("line_item_detection.run tenant=%s", tenant_id)
        new_opps: list[Opportunity] = []
        invoices = (
            await self.session.scalars(select(Invoice).where(Invoice.contract_id.isnot(None)))
        ).all()

        for invoice in invoices:
            if invoice.contract_id is None:
                continue
            lines = (
                await self.session.scalars(
                    select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
                )
            ).all()
            if not lines:
                continue
            cards = await self.rate_cards.for_contract(invoice.contract_id)
            if not cards:
                continue  # no verified rate card → no line-item math (graceful)
            flat, tiered = self.rate_cards.split_tiered(cards)
            mc = await self._match_confidence(invoice.contract_id)

            invoice_opps: list[Opportunity] = []
            if flat:
                ar = detect_above_rate(invoice, list(lines), flat, mc)
                if ar is not None:
                    invoice_opps.append(ar)
            if tiered:
                invoice_opps += detect_volume_tier(
                    invoice.tenant_id, invoice.contract_id, list(lines), tiered, mc
                )
            # Enrich with the invoice's vendor so recovery packs can group by vendor
            # (the pure rules deliberately don't reach for vendor context).
            for o in invoice_opps:
                o.vendor_id = invoice.vendor_id
            new_opps += invoice_opps

        if not new_opps:
            return []

        # Persist line-item opps first so they have ids, then reconcile against the
        # tenant's existing header opps (coexistence dedup), then commit links.
        for o in new_opps:
            self.session.add(o)
        await self.session.flush()

        headers = (
            await self.session.scalars(
                select(Opportunity).where(Opportunity.granularity == "header")
            )
        ).all()
        reconcile([*headers, *new_opps])
        await self.session.commit()
        return new_opps

    async def _match_confidence(self, contract_id: UUID | None) -> Decimal:
        if contract_id is None:
            return _DEFAULT_CONFIDENCE
        conf = await self.session.scalar(
            select(MatchResult.confidence)
            .where(MatchResult.contract_id == contract_id)
            .order_by(MatchResult.confidence.desc())
            .limit(1)
        )
        return conf if conf is not None else _DEFAULT_CONFIDENCE
