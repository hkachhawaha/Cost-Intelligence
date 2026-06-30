"""Detection agent (LangGraph) — L2, deterministic, no LLM.

Runs DetectionService.run_all_rules over the reconciled dataset, persists/updates
opportunities, and emits `opportunities.detected` with code-computed totals.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, StateGraph

from app.core.audit import complete_agent_run, record_agent_run
from app.core.database import session_for_tenant
from app.services.detection import DetectionService
from app.services.events import publish_event
from app.services.scoring import ScoringService

log = logging.getLogger("agent.detection")


class DetectionState(TypedDict, total=False):
    tenant_id: str
    trigger: str
    today: str | None
    agent_run_id: str
    totals: dict
    by_type: dict
    opportunity_count: int
    error: str | None


async def start_run(s: DetectionState) -> DetectionState:
    async with await session_for_tenant(s["tenant_id"]) as session:
        run = await record_agent_run(
            session,
            tenant_id=s["tenant_id"],
            agent="detection",
            trigger=s.get("trigger", "matches.completed"),
        )
        await session.commit()
        return {**s, "agent_run_id": str(run.run_id)}


async def run_and_persist(s: DetectionState) -> DetectionState:
    today_raw = s.get("today")
    today = date.fromisoformat(today_raw) if today_raw else None
    async with await session_for_tenant(s["tenant_id"]) as session:
        svc = DetectionService(session, ScoringService())
        opps = await svc.run_all_rules(
            s["tenant_id"], today=today, agent_run_id=UUID(s["agent_run_id"])
        )
        totals = {"savings": Decimal("0"), "recovery": Decimal("0"), "control": Decimal("0")}
        by_type: dict[str, int] = {}
        for o in opps:
            if o.status not in ("dismissed",):
                totals[o.bucket] += o.impact
                by_type[o.type] = by_type.get(o.type, 0) + 1
        await session.commit()
        opportunity_count = len([o for o in opps if o.status != "dismissed"])

    totals_str = {k: str(v) for k, v in totals.items()}
    totals_str["grand_total"] = str(totals["savings"] + totals["recovery"])
    return {**s, "totals": totals_str, "by_type": by_type, "opportunity_count": opportunity_count}


async def finalize(s: DetectionState) -> DetectionState:
    from app.models.agent_run import AgentRun

    async with await session_for_tenant(s["tenant_id"]) as session:
        run = await session.get(AgentRun, UUID(s["agent_run_id"]))
        if run is not None:
            await complete_agent_run(session, run, status="completed")
        await session.commit()

    await publish_event(
        "opportunities.detected",
        {
            "tenant_id": s["tenant_id"],
            "agent_run_id": s["agent_run_id"],
            "trigger": s.get("trigger", "matches.completed"),
            "opportunity_count": s.get("opportunity_count", 0),
            "totals": s.get("totals", {}),
            "by_type": s.get("by_type", {}),
        },
    )
    return s


def build_detection_graph():
    g = StateGraph(DetectionState)
    for node in (start_run, run_and_persist, finalize):
        g.add_node(node.__name__, node)
    g.set_entry_point("start_run")
    g.add_edge("start_run", "run_and_persist")
    g.add_edge("run_and_persist", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


detection_graph = build_detection_graph()
