"""WorkflowService — the gated automation loop (§2.1, §7).

evaluate_trigger → create_task → assign_owner → schedule_reminder → request_document_draft
→ open_approval_gate (task → awaiting_approval, WAITS). `approve`/`reject` (human action)
record the decision; ONLY an approval reaches `ExternalActionExecutor`. No node performs an
irreversible external action before approval (§5.1).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.automation import Task
from app.services.external_actions import ExternalActionExecutor
from app.services.task import TaskService

logger = logging.getLogger("agent.workflow")

_TASK_TYPE = {"auto_renewal": "non_renewal", "uplift_creep": "renegotiation"}


def is_actionable(opportunity_type: str, confidence: float, deadline: str | None) -> bool:
    """Gate the whole flow — only high-confidence, time-sensitive, allowed-type opps."""
    return (
        confidence >= settings.workflow_min_confidence
        and opportunity_type in settings.workflow_auto_types
        and deadline is not None
    )


class WorkflowService:
    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id
        self.tasks = TaskService(session, tenant_id)

    async def run_for_opportunity(
        self,
        *,
        opportunity_id: str,
        opportunity_type: str,
        confidence: float,
        deadline: str | None,
        workflow_run_id: str | None = None,
        draft_document_id: str | None = None,
    ) -> dict:
        """Drive the pre-approval flow. Returns {skipped} or the awaiting-approval task+gate."""
        if not is_actionable(opportunity_type, confidence, deadline):
            return {"skipped": True}

        task = await self.tasks.create(
            opportunity_id=opportunity_id,
            type=_TASK_TYPE.get(opportunity_type, "review"),
            title=f"Act before notice deadline: {opportunity_type}",
            priority="urgent",
            due_date=datetime.fromisoformat(deadline).date() if deadline else None,
            created_by="ai",
            workflow_run_id=workflow_run_id,
        )
        await self.tasks.set_status(str(task.id), "in_progress")

        owner = await self.tasks.resolve_owner(opportunity_id)
        await self.tasks.assign(str(task.id), owner)

        if deadline:
            fire_at = datetime.fromisoformat(deadline).replace(tzinfo=UTC) - timedelta(
                days=settings.workflow_reminder_lead_days
            )
            await self.tasks.schedule_reminder(str(task.id), fire_at=fire_at)

        # Draft is best-effort (P6 Document agent); the gate doesn't depend on it.
        if draft_document_id:
            await self.tasks.attach_draft(str(task.id), draft_document_id)

        gate = await self.tasks.open_approval_gate(
            str(task.id),
            action_type="external_send",
            action_payload={
                "document_id": draft_document_id,
                "channel": "email",
                "opportunity_id": opportunity_id,
            },
        )
        await self.tasks.set_status(str(task.id), "awaiting_approval")
        return {
            "skipped": False,
            "task_id": str(task.id),
            "approval_gate_id": str(gate.id),
            "owner_id": owner,
        }

    async def approve(self, task_id: str, *, decided_by: str, note: str | None = None) -> dict:
        """HUMAN approval → record decision, then execute the gated external action."""
        gate = await self.tasks.pending_gate_for_task(task_id)
        if gate is None:
            raise ValueError("no pending approval gate for this task")
        await self.tasks.record_decision(
            str(gate.id), approved=True, decided_by=decided_by, note=note
        )
        await self.tasks.set_status(task_id, "approved")
        result = await ExternalActionExecutor(self.session, self.tenant_id).send_document(
            document_id=gate.action_payload.get("document_id"), approval_gate_id=str(gate.id)
        )
        await self.tasks.set_status(task_id, "completed")
        return {"task_id": task_id, "status": "completed", "external_result": result}

    async def reject(self, task_id: str, *, decided_by: str, note: str | None = None) -> dict:
        gate = await self.tasks.pending_gate_for_task(task_id)
        if gate is None:
            raise ValueError("no pending approval gate for this task")
        await self.tasks.record_decision(
            str(gate.id), approved=False, decided_by=decided_by, note=note
        )
        await self.tasks.set_status(task_id, "rejected")
        await self.tasks.set_status(task_id, "cancelled")
        # NOTE: ExternalActionExecutor is never reached on rejection — nothing is sent.
        return {"task_id": task_id, "status": "cancelled"}


def _task_obj(task: Task) -> dict:
    return {
        "id": str(task.id),
        "title": task.title,
        "type": task.type,
        "status": task.status,
        "priority": task.priority,
        "owner_id": str(task.owner_id) if task.owner_id else None,
        "opportunity_id": str(task.opportunity_id) if task.opportunity_id else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
    }
