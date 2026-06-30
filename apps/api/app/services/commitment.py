"""CommitmentCheckService (§6.1, §8.6) — run a deterministic stress test, persist an
immutable advisory record, and record a human sign-off.

The stress-test math lives in `CommitmentControlAgent` (Python Decimal only). This service
persists the verdict, attaches the advisory rationale, and gates sign-off (one decision only —
a second sign-off raises `AlreadySigned`). The platform never signs; a human does.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.commitment_control import commitment_control_agent, write_commitment_rationale
from app.core.audit import record_audit_event
from app.models.commitment import CommitmentCheck
from app.schemas.commitment import CommitmentVerdict, ProposedDeal


class AlreadySigned(ValueError):
    """A commitment check that already carries a sign-off cannot be signed again."""


class CommitmentCheckService:
    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    async def run(self, deal: ProposedDeal, *, requested_by: str | None = None) -> CommitmentCheck:
        verdict: CommitmentVerdict = commitment_control_agent.stress_test(deal)
        verdict.rationale = await write_commitment_rationale(verdict, deal, self.tenant_id)

        check = CommitmentCheck(
            id=uuid4(),
            tenant_id=UUID(self.tenant_id),
            entity_id=UUID(deal.entity_id) if deal.entity_id else None,
            vendor_name=deal.vendor_name,
            proposed_acv=deal.acv,
            proposed_tcv=deal.tcv,
            term_months=deal.term_months,
            indexed_share=deal.indexed_share,
            assumed_index_pct=deal.assumed_index_pct,
            margin_tolerance=deal.margin_tolerance,
            indexed_exposure=verdict.indexed_exposure,
            scenarios={"scenarios": [s.model_dump(mode="json") for s in verdict.scenarios]},
            verdict=verdict.verdict,
            conditions=verdict.conditions,
            rationale=verdict.rationale,
            advisory=True,
            requested_by=UUID(requested_by) if requested_by else None,
        )
        self.session.add(check)
        await self.session.flush()
        await record_audit_event(
            self.session, tenant_id=self.tenant_id, event_type="commitment.checked",
            actor="system",
            payload={"commitment_check_id": str(check.id), "verdict": verdict.verdict,
                     "indexed_exposure": str(verdict.indexed_exposure)},
        )
        return check

    async def get(self, check_id: str) -> CommitmentCheck | None:
        return await self.session.get(CommitmentCheck, UUID(check_id))

    async def list(self) -> list[CommitmentCheck]:
        rows = await self.session.scalars(
            select(CommitmentCheck).order_by(CommitmentCheck.created_at.desc())
        )
        return list(rows.all())

    async def sign(
        self, check_id: str, *, decision: str, signed_by: str, note: str | None = None
    ) -> CommitmentCheck:
        """Record a human sign-off. Idempotency: a second sign-off → AlreadySigned (the
        decision is immutable). The platform itself never signs."""
        check = await self.get(check_id)
        if check is None:
            raise ValueError("commitment check not found")
        if check.signed_at is not None:
            raise AlreadySigned("commitment check already signed")
        check.signed_decision = decision
        check.signed_by = UUID(signed_by)
        check.signed_at = datetime.now(UTC)
        await record_audit_event(
            self.session, tenant_id=self.tenant_id, event_type="commitment.signed",
            actor="human", actor_user_id=UUID(signed_by),
            payload={"commitment_check_id": str(check.id), "decision": decision, "note": note},
        )
        await self.session.flush()
        return check


def commitment_obj(c: CommitmentCheck) -> dict:
    return {
        "id": str(c.id),
        "entity_id": str(c.entity_id) if c.entity_id else None,
        "vendor_name": c.vendor_name,
        "indexed_exposure": str(c.indexed_exposure),
        "scenarios": (c.scenarios or {}).get("scenarios", []),
        "verdict": c.verdict,
        "conditions": c.conditions,
        "rationale": c.rationale,
        "advisory": c.advisory,
        "signed_decision": c.signed_decision,
        "signed_at": c.signed_at.isoformat() if c.signed_at else None,
    }
