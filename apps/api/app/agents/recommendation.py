"""Recommendation agent (LangGraph) — L1, advisory.

For each opportunity, `gemini-2.5-pro` writes a short cited rationale and picks
a document template. The dollar impact is passed in FIXED — the model must never
recompute it. A groundedness guard rejects any rationale containing a dollar
figure other than the fixed impact (the opportunity keeps no rationale rather
than a fabricated one).
"""

from __future__ import annotations

import logging
import re
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, StateGraph

from app.core.database import session_for_tenant
from app.core.model_gateway import model_gateway
from app.models.opportunity import Opportunity

log = logging.getLogger("agent.recommendation")

MODEL = "gemini-2.5-pro"
_VALID_TEMPLATES = {"challenge_letter", "non_renewal_notice", "renegotiation_request", "none"}
_MONEY_RE = re.compile(r"\$?\s?\d[\d,]*(?:\.\d{2})?")

RATIONALE_PROMPT = """\
You are a procurement-finance analyst writing a short, decision-ready rationale for a \
detected cost opportunity. A human will read this to decide whether to act.

ABSOLUTE RULES:
- The dollar impact is ALREADY COMPUTED and is FIXED at ${impact}. You MUST NOT \
recompute it, restate a different number, estimate, or perform ANY arithmetic. If you \
mention the figure, quote it EXACTLY as ${impact}.
- Ground every claim in the evidence provided. Cite the contract and/or record IDs you \
rely on, in the form (contract: {contract_id}) or (invoice: <id>) or (spend: <id>).
- Do NOT invent terms, market comparisons, or external benchmarks — only the evidence below.
- 2-4 sentences. Plain, direct, no fluff.

Opportunity type: {type}   (bucket: {bucket})
Fixed dollar impact: ${impact}
Confidence: {confidence}
Evidence (the transparent formula and its inputs):
{evidence}

Write: (1) what was found and why it matters, citing IDs; (2) the single recommended \
next action. End with one line: RECOMMENDED_TEMPLATE: <one of: challenge_letter, \
non_renewal_notice, renegotiation_request, none>.
"""


class RecommendationState(TypedDict, total=False):
    tenant_id: str
    opportunity: dict
    rationale: str | None
    recommended_template: str
    error: str | None


def _parse_template(text: str) -> str:
    if "RECOMMENDED_TEMPLATE:" in text:
        token = text.split("RECOMMENDED_TEMPLATE:")[-1].strip().split()[0].strip(".,")
        if token in _VALID_TEMPLATES:
            return token
    return "none"


def _is_grounded(text: str, fixed_impact: str) -> bool:
    """Reject any dollar figure that isn't the fixed impact (determinism guard)."""
    allowed = {fixed_impact, fixed_impact.replace(",", ""), f"{float(fixed_impact):,.2f}"}
    for m in _MONEY_RE.findall(text):
        norm = m.replace("$", "").replace(" ", "").strip()
        if not norm:
            continue
        if norm not in allowed and norm.replace(",", "") not in {
            a.replace(",", "") for a in allowed
        }:
            return False
    return True


async def write_rationale(s: RecommendationState) -> RecommendationState:
    opp = s["opportunity"]
    impact = str(opp["impact"])
    prompt = RATIONALE_PROMPT.format(
        impact=impact,
        type=opp["type"],
        bucket=opp["bucket"],
        confidence=opp["confidence"],
        contract_id=opp.get("contract_id"),
        evidence=str(opp["evidence"]),
    )
    try:
        res = await model_gateway.complete(
            MODEL, prompt, tenant_id=s["tenant_id"], purpose="recommendation_rationale"
        )
        text = res.text
    except Exception as exc:  # noqa: BLE001 — advisory only; never block on LLM
        log.warning("rationale generation failed opp=%s: %s", opp.get("id"), exc)
        return {**s, "rationale": None, "recommended_template": "none"}

    template = _parse_template(text)
    rationale = text.split("RECOMMENDED_TEMPLATE:")[0].strip()
    if not _is_grounded(rationale, impact):
        log.warning("rationale ungrounded opp=%s — dropping", opp.get("id"))
        return {**s, "rationale": None, "recommended_template": template}
    return {**s, "rationale": rationale, "recommended_template": template}


async def attach_rationale(s: RecommendationState) -> RecommendationState:
    if s.get("rationale") is None and s.get("recommended_template", "none") == "none":
        return s
    async with await session_for_tenant(s["tenant_id"]) as session:
        opp = await session.get(Opportunity, UUID(str(s["opportunity"]["id"])))
        if opp is not None:
            opp.rationale = s.get("rationale")
            opp.recommended_template = s.get("recommended_template")
            await session.commit()
    return s


def build_recommendation_graph():
    g = StateGraph(RecommendationState)
    for node in (write_rationale, attach_rationale):
        g.add_node(node.__name__, node)
    g.set_entry_point("write_rationale")
    g.add_edge("write_rationale", "attach_rationale")
    g.add_edge("attach_rationale", END)
    return g.compile()


recommendation_graph = build_recommendation_graph()
