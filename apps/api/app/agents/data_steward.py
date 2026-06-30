"""Data Steward agent (L1, deterministic + LLM) — §5.7, §7.4.

Computes data-quality metrics, proposes fixes. Fixes that change REPORTED FIGURES are
gated for human approval (`affects_figures=true`); others auto-apply and are logged
(actor=ai). The LLM writes the rationale prose ONLY — it never computes a figure.
"""

from __future__ import annotations

import logging
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, StateGraph
from sqlalchemy import text

from app.agents.prompts import STEWARD_RATIONALE_PROMPT
from app.core.database import session_for_tenant
from app.core.model_gateway import model_gateway

logger = logging.getLogger("agent.data_steward")

# Proposal types and whether they can change reported numbers.
FIGURE_AFFECTING = {"merge_vendor", "fix_currency", "remap_gl", "reconcile_total"}
NON_FIGURE_AFFECTING = {"fill_missing_metadata", "normalize_name"}


def route_proposal(proposal: dict) -> str:
    """Figure-affecting proposals require human approval; others may auto-apply (still logged)."""
    return "require_approval" if proposal["affects_figures"] else "auto_apply"


class StewardState(TypedDict, total=False):
    tenant_id: str
    run_id: str
    base_currency: str
    quality_metrics: dict
    proposals: list
    error: str | None


async def compute_quality_metrics(s: StewardState) -> StewardState:
    async with await session_for_tenant(s["tenant_id"]) as session:
        row = await session.execute(
            text(
                """
                SELECT COUNT(*) AS spend_rows,
                       COUNT(*) FILTER (WHERE contract_id IS NOT NULL) AS matched_rows,
                       COUNT(*) FILTER (WHERE taxonomy_l1 IS NULL)     AS untaxonomized,
                       COUNT(*) FILTER (WHERE currency <> :base AND base_amount IS NULL)
                            AS unconverted_fx
                FROM spend_records
                """
            ),
            {"base": s.get("base_currency", "USD")},
        )
        first = row.mappings().first()
        m: dict = dict(first) if first else {}
    spend_rows = m.get("spend_rows", 0) or 0
    metrics = {
        "match_coverage_pct": (m.get("matched_rows", 0) / spend_rows) if spend_rows else 0,
        "untaxonomized": m.get("untaxonomized", 0),
        "unconverted_fx": m.get("unconverted_fx", 0),
    }
    return {**s, "quality_metrics": metrics}


async def propose_fixes(s: StewardState) -> StewardState:
    proposals: list[dict] = []
    async with await session_for_tenant(s["tenant_id"]) as session:
        dupes = await session.execute(
            text(
                """
                SELECT a.id AS keep_id, b.id AS merge_id,
                       a.name AS keep_name, b.name AS merge_name
                FROM vendors a JOIN vendors b
                  ON a.tenant_id = b.tenant_id AND a.name_fingerprint = b.name_fingerprint
                 AND a.id < b.id
                """
            )
        )
        rows = dupes.mappings().all()
    for d in rows:
        try:
            rationale = await model_gateway.complete(
                "fast",
                STEWARD_RATIONALE_PROMPT.format(
                    proposal_type="merge_vendor",
                    current=f"two vendor records: '{d['keep_name']}' and '{d['merge_name']}'",
                    proposed=f"merge into '{d['keep_name']}'",
                ),
                tenant_id=s["tenant_id"],
                purpose="steward_rationale",
                run_id=s.get("run_id"),
            )
            rationale_text = rationale.text
        except Exception:  # noqa: BLE001 — rationale is advisory; the gate still holds without it
            rationale_text = None
        proposals.append(
            {
                "proposal_type": "merge_vendor",
                "subject_type": "vendor",
                "subject_id": str(d["merge_id"]),
                "current_value": {"name": d["merge_name"]},
                "proposed_value": {"merge_into": str(d["keep_id"]), "name": d["keep_name"]},
                "affects_figures": True,  # merging vendors changes rollups → GATED
                "rationale": rationale_text,
            }
        )
    return {**s, "proposals": proposals}


async def persist_proposals(s: StewardState) -> StewardState:
    """Figure-affecting → status='proposed' (await approval); others auto-apply + log."""
    from app.models.advanced import StewardProposal

    async with await session_for_tenant(s["tenant_id"]) as session:
        for p in s.get("proposals", []):
            session.add(
                StewardProposal(
                    tenant_id=UUID(s["tenant_id"]),
                    proposal_type=p["proposal_type"],
                    subject_type=p["subject_type"],
                    subject_id=UUID(p["subject_id"]) if p.get("subject_id") else None,
                    current_value=p.get("current_value"),
                    proposed_value=p.get("proposed_value"),
                    affects_figures=p["affects_figures"],
                    rationale=p.get("rationale"),
                    status="proposed" if p["affects_figures"] else "applied",
                    run_id=UUID(s["run_id"]) if s.get("run_id") else None,
                )
            )
        await session.commit()
    return s


def build_steward_graph():
    g = StateGraph(StewardState)
    g.add_node("compute_quality_metrics", compute_quality_metrics)
    g.add_node("propose_fixes", propose_fixes)
    g.add_node("persist_proposals", persist_proposals)
    g.set_entry_point("compute_quality_metrics")
    g.add_edge("compute_quality_metrics", "propose_fixes")
    g.add_edge("propose_fixes", "persist_proposals")
    g.add_edge("persist_proposals", END)
    return g.compile()


steward_graph = build_steward_graph()
