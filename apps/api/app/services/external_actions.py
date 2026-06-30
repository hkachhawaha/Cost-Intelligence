"""ExternalActionExecutor (§5.2) — the ONLY place irreversible external actions fire.

Every action is re-verified against an APPROVED `ApprovalGate` (defense in depth, even
though the workflow already routed here), idempotent (no double-send), and audited with a
reversal note. The actual transport is a stub in this build (no real email/Slack send).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.models.automation import ApprovalGate


class UnapprovedActionError(PermissionError):
    """Raised when an external action is attempted without an approved gate."""


class ExternalActionExecutor:
    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    async def send_document(self, document_id: str | None, approval_gate_id: str) -> dict:
        gate = await self.session.get(ApprovalGate, UUID(approval_gate_id))
        # Defense in depth: refuse unless the gate exists AND is approved.
        if gate is None or gate.decision != "approved":
            raise UnapprovedActionError("external action without an approved gate")
        # Idempotency: never double-send.
        if gate.action_payload.get("executed_at"):
            return {
                "status": "already_sent",
                "external_ref": gate.action_payload.get("external_ref"),
            }

        ref = f"msg-{uuid4().hex[:12]}"  # stub transport; real send wired per channel
        # Persist execution marker on the gate payload (re-assign so the JSONB column updates).
        gate.action_payload = {
            **gate.action_payload,
            "executed_at": datetime.now(UTC).isoformat(),
            "external_ref": ref,
        }
        await record_audit_event(
            self.session,
            tenant_id=self.tenant_id,
            event_type="external_action.executed",
            actor="human",
            actor_user_id=gate.decided_by,
            payload={
                "approval_gate_id": approval_gate_id,
                "document_id": document_id,
                "external_ref": ref,
                "reversal": "compensating-cancel available",
            },
            run_id=gate.workflow_run_id,
        )
        await self.session.flush()
        return {"status": "sent", "external_ref": ref}


external_action_executor = ExternalActionExecutor  # class export
