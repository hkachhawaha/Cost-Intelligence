"""Opportunity lifecycle state machine (§8.3).

Enforces legal transitions, requires an owner before `in_progress`, a reason
before `dismissed`, and an amount on `realized`. Every transition is audited.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.core.audit import record_audit_event
from app.models.opportunity import Opportunity

ALLOWED = {
    "detected": {"triaged", "dismissed"},
    "triaged": {"in_progress", "dismissed"},
    "in_progress": {"realized", "dismissed"},
    "realized": set(),
    "dismissed": set(),
}


class IllegalTransition(ValueError):
    pass


class OpportunityStatusService:
    def __init__(self, session):
        self.session = session

    async def transition(
        self,
        opp: Opportunity,
        to: str,
        principal,
        *,
        dismiss_reason: str | None = None,
        realized_amount: Decimal | None = None,
    ) -> Opportunity:
        if to not in ALLOWED.get(opp.status, set()):
            raise IllegalTransition(f"{opp.status} → {to} not allowed")
        if to == "in_progress" and opp.owner_id is None:
            raise IllegalTransition("owner required before in_progress")
        if to == "dismissed" and not dismiss_reason:
            raise IllegalTransition("dismiss_reason required")

        prior = opp.status
        opp.status = to
        if to == "dismissed":
            opp.dismiss_reason = dismiss_reason
        if to == "realized":
            opp.realized_amount = realized_amount if realized_amount is not None else opp.impact

        await record_audit_event(
            self.session,
            tenant_id=str(opp.tenant_id),
            event_type="opportunity.status_changed",
            actor="human",
            payload={
                "opportunity_id": str(opp.id),
                "from": prior,
                "to": to,
                "user_id": str(principal.user_id),
                "dismiss_reason": dismiss_reason,
                "realized_amount": str(realized_amount) if realized_amount else None,
            },
            run_id=opp.agent_run_id,
        )
        await self.session.flush()
        return opp

    async def assign(self, opp: Opportunity, owner_id: UUID, principal) -> Opportunity:
        prior = opp.owner_id
        opp.owner_id = owner_id
        await record_audit_event(
            self.session,
            tenant_id=str(opp.tenant_id),
            event_type="opportunity.assigned",
            actor="human",
            payload={
                "opportunity_id": str(opp.id),
                "prior_owner": str(prior) if prior else None,
                "new_owner": str(owner_id),
                "user_id": str(principal.user_id),
            },
            run_id=opp.agent_run_id,
        )
        await self.session.flush()
        return opp
