"""Workflow Automation agent (L3, GATED) — §5.1, §7.

LangGraph graph: evaluate_trigger → (skip | run_gated_flow → END). `run_gated_flow`
drives create_task → assign_owner → schedule_reminder → open_approval_gate via
`WorkflowService`, leaving the task at `awaiting_approval`. There is intentionally NO
external-send node in this graph — execution happens only via the human-approval API
(`/tasks/{id}/approve`), so the agent structurally cannot send anything itself (§5.1).
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.core.database import session_for_tenant
from app.services.workflow import WorkflowService, is_actionable


class WorkflowState(TypedDict, total=False):
    tenant_id: str
    opportunity_id: str
    opportunity_type: str
    confidence: float
    deadline: str | None
    run_id: str
    draft_document_id: str | None
    skipped: bool
    task_id: str | None
    approval_gate_id: str | None
    error: str | None


async def evaluate_trigger(s: WorkflowState) -> WorkflowState:
    return {
        **s,
        "skipped": not is_actionable(s["opportunity_type"], s["confidence"], s.get("deadline")),
    }


def route_after_trigger(s: WorkflowState) -> str:
    return "skip" if s.get("skipped") else "run_gated_flow"


async def run_gated_flow(s: WorkflowState) -> WorkflowState:
    async with await session_for_tenant(s["tenant_id"]) as session:
        out = await WorkflowService(session, s["tenant_id"]).run_for_opportunity(
            opportunity_id=s["opportunity_id"],
            opportunity_type=s["opportunity_type"],
            confidence=s["confidence"],
            deadline=s.get("deadline"),
            workflow_run_id=s.get("run_id"),
            draft_document_id=s.get("draft_document_id"),
        )
        await session.commit()
    return {**s, "task_id": out.get("task_id"), "approval_gate_id": out.get("approval_gate_id")}


def build_workflow_graph():
    g = StateGraph(WorkflowState)
    g.add_node("evaluate_trigger", evaluate_trigger)
    g.add_node("run_gated_flow", run_gated_flow)
    g.set_entry_point("evaluate_trigger")
    g.add_conditional_edges(
        "evaluate_trigger", route_after_trigger, {"skip": END, "run_gated_flow": "run_gated_flow"}
    )
    g.add_edge("run_gated_flow", END)
    return g.compile()


# Node names that perform an external action — MUST be empty (the gate is API-side).
EXTERNAL_ACTION_NODES: set[str] = set()

workflow_graph = build_workflow_graph()
