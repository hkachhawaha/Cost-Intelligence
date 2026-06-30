"""MatchingService — the deterministic spend↔contract matching core (§8.2).

Pure Python; no LLM here (AI inference is a separate agent node). Tiers:
  1. PO-exact (confidence 1.0)
  2. Weighted fuzzy: vendor 0.4 · amount 0.3 · date 0.2 · cost_center 0.1
  3. (AI inference happens in the agent)
  4. Unmatched → unmatched_queue (maverick, never hidden)
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_event
from app.core.tenancy import current_tenant
from app.models.contract import Contract
from app.models.matching import MatchResult, UnmatchedQueue
from app.models.spend import SpendRecord
from app.services.matching_candidates import CandidateRetrievalService

log = logging.getLogger("matching")

# Fuzzy weights (must sum to 1.0) — blueprint §8.2.
W_VENDOR = Decimal("0.4")
W_AMOUNT = Decimal("0.3")
W_DATE = Decimal("0.2")
W_COST_CENTER = Decimal("0.1")

FUZZY_FLOOR = Decimal("0.50")  # below ⇒ unmatched
REVIEW_THRESHOLD = Decimal("0.70")  # below ⇒ human review
SPOT_CHECK_THRESHOLD = Decimal("0.90")
DATE_WINDOW_DAYS = 45  # date_proximity decays to 0 at this span

assert W_VENDOR + W_AMOUNT + W_DATE + W_COST_CENTER == Decimal("1.0"), "fuzzy weights must sum to 1"


class MatchingService:
    def __init__(self, session: AsyncSession, candidates: CandidateRetrievalService):
        self.session = session
        self.candidates = candidates

    # ── Tier 1 — deterministic PO match (confidence 1.0) ──────────────────
    def match_by_po(self, spend: SpendRecord, candidates: list[Contract]) -> MatchResult | None:
        if not spend.po_number:
            return None
        po = spend.po_number.strip().upper()
        for c in candidates:
            contract_pos = {p.strip().upper() for p in (c.po_numbers or [])}
            if po in contract_pos:
                return self._build_result(
                    spend,
                    c,
                    method="po_exact",
                    confidence=Decimal("1.000"),
                    scenario=self._scenario_for(spend, c),
                    score_breakdown={"po": "1.0", "weighted": "1.0"},
                    discrepancies=self._discrepancies(spend, c),
                )
        return None

    # ── Tier 2 — weighted fuzzy match (confidence 0.50–0.95) ──────────────
    def match_by_vendor_amount_date(
        self, spend: SpendRecord, candidates: list[Contract]
    ) -> MatchResult | None:
        scored: list[tuple[Contract, Decimal, dict]] = []
        for c in candidates:
            score, breakdown = self._fuzzy_score(spend, c)
            scored.append((c, score, breakdown))
        if not scored:
            return None
        scored.sort(key=lambda t: t[1], reverse=True)
        best_contract, best_score, best_breakdown = scored[0]
        if best_score < FUZZY_FLOOR:
            return None

        confidence = min(best_score, Decimal("0.950"))  # fuzzy never claims PO certainty
        scenario = (
            3
            if len(scored) > 1 and scored[1][1] >= FUZZY_FLOOR
            else self._scenario_for(spend, best_contract)
        )
        discrepancies = self._discrepancies(spend, best_contract)
        discrepancies["alternatives"] = [
            {"contract_id": str(c.id), "score": str(round(s, 3))}
            for c, s, _ in scored[1:4]
            if s >= FUZZY_FLOOR
        ]
        return self._build_result(
            spend,
            best_contract,
            method="vendor_amount_date",
            confidence=confidence,
            scenario=scenario,
            score_breakdown=best_breakdown,
            discrepancies=discrepancies,
        )

    def _fuzzy_score(self, spend: SpendRecord, c: Contract) -> tuple[Decimal, dict]:
        vendor = Decimal("1.0") if spend.vendor_id == c.vendor_id else Decimal("0.0")
        amount = self._amount_similarity(spend.amount, c.acv)
        date_s = self._date_proximity(spend.spend_date, c.start_date, c.end_date)
        cc = self._cost_center_match(spend, c)
        weighted = W_VENDOR * vendor + W_AMOUNT * amount + W_DATE * date_s + W_COST_CENTER * cc
        breakdown = {
            "vendor": str(vendor),
            "amount": str(round(amount, 3)),
            "date": str(round(date_s, 3)),
            "cost_center": str(cc),
            "weights": {"vendor": "0.4", "amount": "0.3", "date": "0.2", "cost_center": "0.1"},
            "weighted": str(round(weighted, 3)),
        }
        return weighted, breakdown

    @staticmethod
    def _amount_similarity(spend_amount: Decimal, acv: Decimal | None) -> Decimal:
        """1 − |spend − monthly_acv| / max(spend, monthly_acv, 1), clamped to [0,1]."""
        if not acv or acv <= 0:
            return Decimal("0.0")
        monthly = acv / Decimal("12")
        denom = max(spend_amount, monthly, Decimal("1"))
        sim = Decimal("1") - (abs(spend_amount - monthly) / denom)
        return max(Decimal("0.0"), min(Decimal("1.0"), sim))

    @staticmethod
    def _date_proximity(spend_date: date, start: date | None, end: date | None) -> Decimal:
        if start is None or end is None:
            return Decimal("0.0")
        if start <= spend_date <= end:
            return Decimal("1.0")
        days_outside = (start - spend_date).days if spend_date < start else (spend_date - end).days
        decayed = Decimal("1") - (Decimal(days_outside) / Decimal(DATE_WINDOW_DAYS))
        return max(Decimal("0.0"), decayed)

    @staticmethod
    def _cost_center_match(spend: SpendRecord, c: Contract) -> Decimal:
        if spend.cost_center and c.entity_id and str(spend.cost_center) == str(c.entity_id):
            return Decimal("1.0")
        return Decimal("0.0")

    # ── Orchestration (Tier 1 → Tier 2; unmatched stub otherwise) ─────────
    async def match_spend_record(self, spend: SpendRecord) -> MatchResult:
        candidates = await self.candidates.for_spend(spend)
        result = self.match_by_po(spend, candidates)
        if result is not None:
            return result
        result = self.match_by_vendor_amount_date(spend, candidates)
        if result is not None:
            return result
        return self._unmatched(
            spend, reason="no_candidate" if not candidates else "below_threshold"
        )

    # ── Human override ────────────────────────────────────────────────────
    async def accept_human_match(
        self, match_id: UUID, principal, contract_id: UUID | None, reason: str
    ) -> MatchResult:
        mr = await self.session.get(MatchResult, match_id)
        if mr is None or str(mr.tenant_id) != current_tenant.get():
            raise ValueError("match_result not found in tenant scope")

        prior = {
            "contract_id": str(mr.contract_id),
            "confidence": str(mr.confidence),
            "method": mr.method,
            "status": mr.status,
        }
        mr.contract_id = contract_id
        mr.method = (
            "po_exact"
            if mr.method == "po_exact" and contract_id
            else ("vendor_amount_date" if contract_id else "unmatched")
        )
        mr.matched_by = "human"
        mr.human_override_reason = reason
        mr.confidence = Decimal("1.000") if contract_id else Decimal("0.000")
        mr.status = "reassigned" if contract_id else "unmatched"
        if contract_id:
            mr.match_chain = {**mr.match_chain, "contract_id": str(contract_id), "overridden": True}

        uq = (
            await self.session.execute(
                select(UnmatchedQueue).where(UnmatchedQueue.spend_id == mr.spend_id)
            )
        ).scalar_one_or_none()
        if uq is not None:
            uq.status = "matched" if contract_id else "accepted_maverick"
            uq.resolved_by = UUID(principal.user_id) if _is_uuid(principal.user_id) else None
            uq.resolved_at = _utcnow()

        await record_audit_event(
            self.session,
            tenant_id=str(mr.tenant_id),
            event_type="match.human_override",
            actor="human",
            payload={
                "match_id": str(match_id),
                "prior": prior,
                "new_contract_id": str(contract_id),
                "reason": reason,
                "user_id": str(principal.user_id),
            },
            run_id=mr.agent_run_id,
        )
        await self.session.flush()
        log.info("human override match=%s contract=%s", match_id, contract_id)
        return mr

    # ── Full-tenant re-match (Refresh path) ───────────────────────────────
    async def run_full_tenant_match(self, tenant_id: str, agent_run_id: UUID | None = None) -> dict:
        spend_rows = (
            (
                await self.session.execute(
                    select(SpendRecord).where(SpendRecord.tenant_id == UUID(tenant_id))
                )
            )
            .scalars()
            .all()
        )

        counts = {
            "po_exact": 0,
            "vendor_amount_date": 0,
            "ai_inferred": 0,
            "unmatched": 0,
            "preserved_human": 0,
        }
        for spend in spend_rows:
            existing = (
                await self.session.execute(
                    select(MatchResult).where(MatchResult.spend_id == spend.id)
                )
            ).scalar_one_or_none()
            if existing is not None and existing.matched_by == "human":
                counts["preserved_human"] += 1
                continue
            result = await self.match_spend_record(spend)
            if agent_run_id is not None:
                result.agent_run_id = agent_run_id
            persisted = await self._persist(result, existing)
            await self._sync_unmatched_queue(persisted, spend)
            counts[result.method] += 1
        await self.session.flush()
        return counts

    # ── Helpers ───────────────────────────────────────────────────────────
    def _build_result(
        self, spend, contract, *, method, confidence, scenario, score_breakdown, discrepancies
    ) -> MatchResult:
        invoice_id = getattr(spend, "invoice_id", None)
        return MatchResult(
            tenant_id=spend.tenant_id,
            spend_id=spend.id,
            contract_id=contract.id,
            invoice_id=invoice_id,
            method=method,
            scenario=scenario,
            confidence=confidence,
            status=self._classify(confidence),
            score_breakdown=score_breakdown,
            discrepancies=discrepancies,
            match_chain={
                "scenario": scenario,
                "contract_id": str(contract.id),
                "invoice_id": str(invoice_id) if invoice_id else None,
                "spend_id": str(spend.id),
                "inferred": method == "ai_inferred",
            },
            matched_by="system",
        )

    def _unmatched(self, spend, *, reason: str) -> MatchResult:
        return MatchResult(
            tenant_id=spend.tenant_id,
            spend_id=spend.id,
            contract_id=None,
            invoice_id=None,
            method="unmatched",
            scenario=1,
            confidence=Decimal("0.000"),
            status="unmatched",
            score_breakdown={},
            discrepancies={"reason": reason},
            match_chain={
                "scenario": 1,
                "contract_id": None,
                "spend_id": str(spend.id),
                "inferred": False,
            },
            matched_by="system",
        )

    @staticmethod
    def _classify(confidence: Decimal) -> str:
        if confidence >= SPOT_CHECK_THRESHOLD:
            return "accepted"
        if confidence >= REVIEW_THRESHOLD:
            return "spot_check"
        if confidence >= FUZZY_FLOOR:
            return "needs_review"
        return "unmatched"

    @staticmethod
    def _scenario_for(spend, contract) -> int:
        return 1 if getattr(spend, "invoice_id", None) else 2

    @staticmethod
    def _discrepancies(spend, contract) -> dict:
        d: dict = {}
        monthly = (contract.acv / Decimal("12")) if contract.acv else None
        if monthly is not None and abs(spend.amount - monthly) > (monthly * Decimal("0.05")):
            d["amount"] = {"expected_monthly": str(round(monthly, 2)), "actual": str(spend.amount)}
        if (
            contract.start_date
            and contract.end_date
            and not (contract.start_date <= spend.spend_date <= contract.end_date)
        ):
            d["date"] = {
                "contract_term": f"{contract.start_date}..{contract.end_date}",
                "spend_date": spend.spend_date.isoformat(),
            }
        return d

    async def _persist(self, result: MatchResult, existing: MatchResult | None) -> MatchResult:
        if existing is not None:
            for field in (
                "contract_id",
                "invoice_id",
                "method",
                "scenario",
                "confidence",
                "status",
                "discrepancies",
                "match_chain",
                "score_breakdown",
                "agent_run_id",
            ):
                setattr(existing, field, getattr(result, field))
            existing.matched_by = "system"
            await self.session.flush()
            return existing
        self.session.add(result)
        await self.session.flush()
        return result

    async def _sync_unmatched_queue(self, result: MatchResult, spend: SpendRecord) -> None:
        """Keep unmatched_queue in lockstep with the match result (DoD: maverick never hidden)."""
        existing = (
            await self.session.execute(
                select(UnmatchedQueue).where(UnmatchedQueue.spend_id == spend.id)
            )
        ).scalar_one_or_none()
        if result.method == "unmatched":
            reason = result.discrepancies.get("reason", "no_candidate")
            if reason not in ("no_po_match", "no_candidate", "below_threshold", "ai_no_candidate"):
                reason = "no_candidate"
            if existing is None:
                self.session.add(
                    UnmatchedQueue(
                        tenant_id=spend.tenant_id,
                        spend_id=spend.id,
                        match_result_id=result.id,
                        vendor_id=spend.vendor_id,
                        vendor_name=spend.vendor_name_raw or "",
                        amount=spend.amount,
                        currency=spend.currency,
                        spend_date=spend.spend_date,
                        po_number=spend.po_number,
                        reason=reason,
                        status="pending",
                    )
                )
            elif existing.status == "pending":
                existing.reason = reason
        elif existing is not None and existing.status == "pending":
            # Now matched by the system → close the stale pending maverick row.
            existing.status = "matched"
            existing.match_result_id = result.id


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_uuid(v) -> bool:
    try:
        UUID(str(v))
        return True
    except (ValueError, TypeError):
        return False
