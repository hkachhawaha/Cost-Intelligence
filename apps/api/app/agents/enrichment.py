"""Enrichment agent (L2, gemini-2.5-flash) — §7.1.

Per staged record: first-party FX → base_amount; canonical vendor resolution; L1/L2
taxonomy (rules-first, haiku fallback). Low-confidence taxonomy is routed to a HITL
spot-check queue. Persists taxonomy/base_amount/fx/vendor_id back to spend_records (L2,
reversible). Triggered by `records.landed` (Phase 1) ahead of Matching.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, StateGraph
from sqlalchemy import update

from app.core.config import settings
from app.core.database import session_for_tenant
from app.services.currency import currency_service
from app.services.taxonomy import taxonomy_service
from app.services.vendor_normalization import VendorNormalizationService

logger = logging.getLogger("agent.enrichment")


class EnrichmentState(TypedDict, total=False):
    tenant_id: str
    batch_id: str
    run_id: str
    staged: list[dict]  # records to enrich
    base_currency: str
    enriched: list[dict]
    spot_check: list[dict]
    error: str | None


async def normalize_currency(s: EnrichmentState) -> EnrichmentState:
    base = s.get("base_currency") or settings.tenant_base_currency
    enriched = []
    for rec in s["staged"]:
        base_amount, fx_rate = currency_service.to_base(
            Decimal(str(rec["amount"])), rec.get("currency", "USD"), base
        )
        enriched.append({**rec, "base_amount": str(base_amount), "fx_rate": str(fx_rate)})
    return {**s, "enriched": enriched}


async def refine_vendor(s: EnrichmentState) -> EnrichmentState:
    out = []
    async with await session_for_tenant(s["tenant_id"]) as session:
        norm = VendorNormalizationService(session, s["tenant_id"])
        for rec in s["enriched"]:
            vendor = await norm.get_or_create_canonical(rec.get("vendor_name", "Unknown"))
            out.append({**rec, "vendor_id": str(vendor.id)})
        await session.commit()
    return {**s, "enriched": out}


async def classify_taxonomy(s: EnrichmentState) -> EnrichmentState:
    out, spot_check = [], []
    for rec in s["enriched"]:
        result = await taxonomy_service.classify(
            tenant_id=s["tenant_id"],
            vendor_name=rec.get("vendor_name", ""),
            gl_code=rec.get("gl_code"),
            description=rec.get("description"),
            run_id=s.get("run_id"),
        )
        rec = {
            **rec,
            "taxonomy_l1": result.l1,
            "taxonomy_l2": result.l2,
            "enrichment_confidence": result.confidence,
        }
        out.append(rec)
        if result.confidence < settings.taxonomy_low_confidence:
            spot_check.append(rec)  # low-confidence → HITL spot-check
    return {**s, "enriched": out, "spot_check": spot_check}


async def persist_enriched(s: EnrichmentState) -> EnrichmentState:
    """Write taxonomy/base_amount/fx/vendor back to spend_records (L2, reversible)."""
    from app.models.spend import SpendRecord

    async with await session_for_tenant(s["tenant_id"]) as session:
        for rec in s["enriched"]:
            if not rec.get("spend_id"):
                continue
            await session.execute(
                update(SpendRecord)
                .where(SpendRecord.id == UUID(str(rec["spend_id"])))
                .values(
                    taxonomy_l1=rec.get("taxonomy_l1"),
                    taxonomy_l2=rec.get("taxonomy_l2"),
                    base_amount=Decimal(rec["base_amount"]) if rec.get("base_amount") else None,
                    fx_rate=Decimal(rec["fx_rate"]) if rec.get("fx_rate") else None,
                    enrichment_confidence=rec.get("enrichment_confidence"),
                )
            )
        await session.commit()
    return s


def build_enrichment_graph():
    g = StateGraph(EnrichmentState)
    for n in (normalize_currency, refine_vendor, classify_taxonomy, persist_enriched):
        g.add_node(n.__name__, n)
    g.set_entry_point("normalize_currency")
    g.add_edge("normalize_currency", "refine_vendor")
    g.add_edge("refine_vendor", "classify_taxonomy")
    g.add_edge("classify_taxonomy", "persist_enriched")
    g.add_edge("persist_enriched", END)
    return g.compile()


enrichment_graph = build_enrichment_graph()
