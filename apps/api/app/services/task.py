"""TaskService (§5.3) — workflow task state machine, approval gates, reminders.

The state machine + the persisted `ApprovalGate` are the gated-automation control: a task
reaches `awaiting_approval` and waits; only a recorded `approved` decision authorizes the
external action. Every transition and decision is audited.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.models.automation import ApprovalGate, Task, TaskReminder

VALID_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "cancelled"},
    "in_progress": {"awaiting_approval", "cancelled", "completed"},
    "awaiting_approval": {"approved", "rejected"},
    "approved": {"completed"},
    "rejected": {"cancelled"},
    "completed": set(),
    "cancelled": set(),
}


class IllegalTaskTransition(ValueError): ...


class GateAlreadyDecided(ValueError): ...


class TaskService:
    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    async def create(
        self,
        *,
        opportunity_id: str | None,
        type: str,
        title: str,
        priority: str = "normal",
        due_date=None,
        created_by: str = "ai",
        workflow_run_id: str | None = None,
    ) -> Task:
        task = Task(
            id=uuid4(),
            tenant_id=UUID(self.tenant_id),
            opportunity_id=UUID(opportunity_id) if opportunity_id else None,
            type=type,
            title=title,
            priority=priority,
            status="open",
            due_date=due_date,
            created_by=created_by,
            workflow_run_id=UUID(workflow_run_id) if workflow_run_id else None,
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def get(self, task_id: str) -> Task | None:
        return await self.session.get(Task, UUID(task_id))

    async def assign(self, task_id: str, owner_id: str | None) -> None:
        task = await self._require(task_id)
        task.owner_id = UUID(owner_id) if owner_id else None
        await self.session.flush()

    async def resolve_owner(self, opportunity_id: str | None) -> str | None:
        """Resolve a task owner. v2 heuristic: the opportunity's existing owner, if any."""
        if not opportunity_id:
            return None
        from app.models.opportunity import Opportunity

        opp = await self.session.get(Opportunity, UUID(opportunity_id))
        return str(opp.owner_id) if opp and opp.owner_id else None

    async def schedule_reminder(
        self, task_id: str, *, fire_at: datetime, channel: str = "email"
    ) -> TaskReminder:
        rem = TaskReminder(
            id=uuid4(),
            tenant_id=UUID(self.tenant_id),
            task_id=UUID(task_id),
            fire_at=fire_at,
            channel=channel,
        )
        self.session.add(rem)
        task = await self._require(task_id)
        task.reminder_at = fire_at
        await self.session.flush()
        return rem

    async def attach_draft(self, task_id: str, document_id: str | None) -> None:
        task = await self._require(task_id)
        task.draft_document_id = UUID(document_id) if document_id else None
        await self.session.flush()

    async def set_status(self, task_id: str, new: str) -> None:
        task = await self._require(task_id)
        if new == task.status:
            return
        if new not in VALID_TRANSITIONS.get(task.status, set()):
            raise IllegalTaskTransition(f"{task.status} → {new}")
        prior = task.status
        task.status = new
        await record_audit_event(
            self.session,
            tenant_id=self.tenant_id,
            event_type="task.status_changed",
            actor="system",
            payload={"task_id": task_id, "from": prior, "to": new},
        )
        await self.session.flush()

    async def open_approval_gate(
        self, task_id: str, action_type: str, action_payload: dict
    ) -> ApprovalGate:
        gate = ApprovalGate(
            id=uuid4(),
            tenant_id=UUID(self.tenant_id),
            task_id=UUID(task_id),
            action_type=action_type,
            action_payload=action_payload,
            decision="pending",
        )
        self.session.add(gate)
        await self.session.flush()
        return gate

    async def get_gate(self, gate_id: str) -> ApprovalGate | None:
        return await self.session.get(ApprovalGate, UUID(gate_id))

    async def pending_gate_for_task(self, task_id: str) -> ApprovalGate | None:
        return await self.session.scalar(
            select(ApprovalGate)
            .where(ApprovalGate.task_id == UUID(task_id))
            .where(ApprovalGate.decision == "pending")
        )

    async def record_decision(
        self,
        gate_id: str,
        *,
        approved: bool,
        decided_by: str | None = None,
        note: str | None = None,
    ) -> ApprovalGate:
        gate = await self.get_gate(gate_id)
        if gate is None:
            raise GateAlreadyDecided("gate not found")
        if gate.decision != "pending":
            raise GateAlreadyDecided("gate already decided")  # idempotent / no re-decision
        gate.decision = "approved" if approved else "rejected"
        gate.decided_by = UUID(decided_by) if decided_by else None
        gate.decided_at = datetime.now(UTC)
        gate.decision_note = note
        await record_audit_event(
            self.session,
            tenant_id=self.tenant_id,
            event_type="approval.decided",
            actor="human",
            actor_user_id=UUID(decided_by) if decided_by else None,
            payload={
                "gate_id": gate_id,
                "task_id": str(gate.task_id),
                "decision": gate.decision,
                "note": note,
            },
        )
        await self.session.flush()
        return gate

    async def _require(self, task_id: str) -> Task:
        task = await self.get(task_id)
        if task is None:
            raise ValueError(f"task {task_id} not found")
        return task
