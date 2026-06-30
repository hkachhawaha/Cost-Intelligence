"""DetectionService — runs all 8 v1 rules over the reconciled dataset and
upserts Opportunities idempotently by (type, contract_id).

Every dollar figure originates in a pure rule function (§5.6). The service only
loads data, dispatches rules, scores, and persists.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.matching import MatchResult
from app.models.opportunity import Opportunity, RecoveryItem
from app.models.spend import SpendRecord
from app.services.rules._types import RuleFinding
from app.services.rules.auto_renewal import detect_silent_auto_renewal
from app.services.rules.duplicate_invoice import detect_duplicate_invoices
from app.services.rules.maverick import detect_maverick
from app.services.rules.missing_invoice import detect_missing_invoice
from app.services.rules.overspend import detect_overspend
from app.services.rules.post_expiry import detect_post_expiry
from app.services.rules.unused_commitment import detect_unused_commitment
from app.services.rules.uplift_creep import detect_uplift_creep
from app.services.scoring import ScoringService

log = logging.getLogger("detection")


class DetectionService:
    def __init__(
        self,
        session: AsyncSession,
        scoring: ScoringService,
        recapture_rate: Decimal = Decimal("0.15"),
    ):
        self.session = session
        self.scoring = scoring
        self.recapture_rate = recapture_rate

    async def run_all_rules(
        self, tenant_id: str, today: date | None = None, agent_run_id: UUID | None = None
    ) -> list[Opportunity]:
        today = today or date.today()
        data = await self._load_reconciled(tenant_id)
        findings = self.run_rules_over(data, today)
        ranked = self.scoring.rank(findings)
        opportunities = await self._upsert(UUID(tenant_id), ranked, agent_run_id)
        log.info(
            "detection tenant=%s findings=%d opps=%d", tenant_id, len(findings), len(opportunities)
        )
        return opportunities

    def run_rules_over(self, data: dict, today: date) -> list[RuleFinding]:
        """Pure dispatch over an in-memory reconciled dataset (shared with the eval harness)."""
        findings: list[RuleFinding] = []
        # Tenant-wide rules.
        findings += detect_maverick(data["unmatched_spend"], self.recapture_rate)
        findings += detect_duplicate_invoices(data["invoices"])
        # Per-contract rules — each wrapped so one bad contract can't abort the run.
        for c in data["contracts"]:
            cid = c["id"]
            matched = data["matched_by_contract"].get(cid, [])
            matched_total = sum((Decimal(str(s["amount"])) for s in matched), Decimal("0"))
            conf = data["confidence_by_contract"].get(cid, Decimal("0.000"))
            matched_ids = [str(s["spend_id"]) for s in matched]
            invoice_pos = data["invoice_pos_by_contract"].get(cid, set())
            for finding in (
                detect_silent_auto_renewal(c, today),
                detect_uplift_creep(c),
                detect_unused_commitment(c, matched_total, conf),
                detect_overspend(c, matched_total, conf, matched_ids),
                detect_post_expiry(c, matched, conf),
                detect_missing_invoice(c, matched, invoice_pos, conf),
            ):
                if finding is not None and finding.impact > 0:
                    findings.append(finding)
        return findings

    @staticmethod
    def _dedup_key(f: RuleFinding) -> tuple:
        if f.type == "duplicate_invoice" and f.contract_id is None:
            return (f.type, None, f.evidence.get("invoice_number"))
        return (f.type, str(f.contract_id) if f.contract_id else None)

    def _key_of(self, opp: Opportunity) -> tuple:
        if opp.type == "duplicate_invoice" and opp.contract_id is None:
            return (opp.type, None, opp.evidence.get("invoice_number"))
        return (opp.type, str(opp.contract_id) if opp.contract_id else None)

    async def _upsert(
        self, tenant_id: UUID, findings: list[RuleFinding], agent_run_id: UUID | None
    ) -> list[Opportunity]:
        existing = (
            (
                await self.session.execute(
                    select(Opportunity).where(
                        Opportunity.tenant_id == tenant_id,
                        Opportunity.status.notin_(("realized", "dismissed")),
                    )
                )
            )
            .scalars()
            .all()
        )
        existing_by_key = {self._key_of(o): o for o in existing}
        seen: set = set()
        out: list[Opportunity] = []

        for f in findings:
            key = self._dedup_key(f)
            seen.add(key)
            opp = existing_by_key.get(key)
            if opp is not None:
                # Update figures; preserve status/owner (§2.3).
                opp.impact = f.impact
                opp.confidence = f.confidence
                opp.bucket = f.bucket
                opp.evidence = f.evidence
                opp.time_sensitivity = f.time_sensitivity
                opp.effort = f.effort
                opp.rank_score = f.impact * f.confidence
                if agent_run_id is not None:
                    opp.agent_run_id = agent_run_id
            else:
                opp = Opportunity(
                    tenant_id=tenant_id,
                    contract_id=f.contract_id,
                    vendor_id=f.vendor_id,
                    type=f.type,
                    bucket=f.bucket,
                    impact=f.impact,
                    confidence=f.confidence,
                    rank_score=f.impact * f.confidence,
                    time_sensitivity=f.time_sensitivity,
                    effort=f.effort,
                    evidence=f.evidence,
                    status="detected",
                    agent_run_id=agent_run_id,
                )
                self.session.add(opp)
                await self.session.flush()
                await self._attach_recovery_items(opp, f)
            out.append(opp)

        # Auto-dismiss vanished opportunities (no longer detected).
        for key, opp in existing_by_key.items():
            if key not in seen and opp.status in ("detected", "triaged"):
                opp.status = "dismissed"
                opp.dismiss_reason = "no_longer_detected"
                await record_audit_event(
                    self.session,
                    tenant_id=str(opp.tenant_id),
                    event_type="opportunity.auto_dismissed",
                    actor="ai",
                    payload={"opportunity_id": str(opp.id), "type": opp.type},
                    run_id=opp.agent_run_id,
                )

        await self.session.flush()
        return out

    async def _attach_recovery_items(self, opp: Opportunity, f: RuleFinding) -> None:
        for ri in f.recovery_items:
            self.session.add(
                RecoveryItem(
                    tenant_id=opp.tenant_id,
                    opp_id=opp.id,
                    amount=Decimal(ri["amount"]),
                    evidence=ri.get("evidence", {}),
                )
            )

    async def _load_reconciled(self, tenant_id: str) -> dict:
        tid = UUID(tenant_id)
        contracts_rows = (
            (await self.session.execute(select(Contract).where(Contract.tenant_id == tid)))
            .scalars()
            .all()
        )
        spend_rows = (
            (await self.session.execute(select(SpendRecord).where(SpendRecord.tenant_id == tid)))
            .scalars()
            .all()
        )
        spend_by_id = {s.id: s for s in spend_rows}
        mr_rows = (
            (await self.session.execute(select(MatchResult).where(MatchResult.tenant_id == tid)))
            .scalars()
            .all()
        )
        invoice_rows = (
            (await self.session.execute(select(Invoice).where(Invoice.tenant_id == tid)))
            .scalars()
            .all()
        )

        matched_by_contract: dict[UUID, list] = defaultdict(list)
        confidence_lists: dict[UUID, list[Decimal]] = defaultdict(list)
        unmatched_spend: list[dict] = []
        for mr in mr_rows:
            s = spend_by_id.get(mr.spend_id)
            if s is None:
                continue
            if mr.method == "unmatched" or mr.contract_id is None:
                unmatched_spend.append(
                    {"spend_id": s.id, "amount": s.amount, "vendor_name": s.vendor_name_raw}
                )
            else:
                matched_by_contract[mr.contract_id].append(
                    {
                        "spend_id": s.id,
                        "amount": s.amount,
                        "spend_date": s.spend_date,
                        "po_number": s.po_number,
                    }
                )
                confidence_lists[mr.contract_id].append(mr.confidence)
        confidence_by_contract = {cid: min(confs) for cid, confs in confidence_lists.items()}

        invoice_pos_by_contract: dict[UUID, set] = defaultdict(set)
        for i in invoice_rows:
            if i.contract_id and i.po_number:
                invoice_pos_by_contract[i.contract_id].add(i.po_number)

        return {
            "contracts": [self._contract_dict(c) for c in contracts_rows],
            "matched_by_contract": matched_by_contract,
            "confidence_by_contract": confidence_by_contract,
            "unmatched_spend": unmatched_spend,
            "invoices": [
                {
                    "id": i.id,
                    "vendor_id": i.vendor_id,
                    "invoice_number": i.invoice_number,
                    "total_amount": i.total_amount,
                    "status": i.status,
                    "contract_id": i.contract_id,
                }
                for i in invoice_rows
            ],
            "invoice_pos_by_contract": invoice_pos_by_contract,
        }

    @staticmethod
    def _contract_dict(c: Contract) -> dict:
        return {
            "id": c.id,
            "vendor_id": c.vendor_id,
            "acv": c.acv,
            "tcv": c.tcv,
            "yearly_commit": c.yearly_commit,
            "uplift_pct": c.uplift_pct,
            "renewal_type": c.renewal_type,
            "renewal_notice_days": c.renewal_notice_days,
            "end_date": c.end_date,
        }
