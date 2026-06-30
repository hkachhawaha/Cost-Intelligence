"""DocumentService (§5.4) — the 5 document templates + RBAC-scoped context assembly.

Each template declares when it's used, what (code-computed) context it pulls, and a
prompt skeleton. The LLM drafts prose ONLY; every figure comes from the assembled
context and is groundedness-validated downstream. Context assembly is tenant-scoped
(RLS session) and raises `PermissionError` when the record isn't authorized.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal


class DocumentNotAuthorizedError(PermissionError):
    """Context record not found for this tenant or not authorized for the principal."""


@dataclass
class DocumentTemplate:
    key: str
    title_tpl: str
    when_used: str
    context_kind: str  # 'opportunity'|'contract'|'vendor'
    prompt_skeleton: str  # name of the DOC_SKELETON_* constant (see agents/prompts.py)


TEMPLATES: dict[str, DocumentTemplate] = {
    "supplier_challenge": DocumentTemplate(
        key="supplier_challenge",
        title_tpl="Supplier Challenge — {vendor}",
        when_used="Margin Recovery: package recoverable items for a supplier challenge.",
        context_kind="opportunity",
        prompt_skeleton="DOC_SKELETON_SUPPLIER_CHALLENGE",
    ),
    "non_renewal": DocumentTemplate(
        key="non_renewal",
        title_tpl="Non-Renewal Notice — {vendor}",
        when_used="Renewals: a contract is auto-renewing inside its notice window; do not renew.",
        context_kind="contract",
        prompt_skeleton="DOC_SKELETON_NON_RENEWAL",
    ),
    "renegotiation": DocumentTemplate(
        key="renegotiation",
        title_tpl="Renegotiation Request — {vendor}",
        when_used="Renewals/Opportunities: push back on a quantified negotiable uplift.",
        context_kind="opportunity",
        prompt_skeleton="DOC_SKELETON_RENEGOTIATION",
    ),
    "rfp_brief": DocumentTemplate(
        key="rfp_brief",
        title_tpl="RFP Brief — {category}",
        when_used="Spend Explorer: a fragmented category is a consolidation/sourcing candidate.",
        context_kind="vendor",
        prompt_skeleton="DOC_SKELETON_RFP_BRIEF",
    ),
    "supplier_swot": DocumentTemplate(
        key="supplier_swot",
        title_tpl="Supplier SWOT — {vendor}",
        when_used="Vendors: prepare for a supplier conversation with a first-party SWOT.",
        context_kind="vendor",
        prompt_skeleton="DOC_SKELETON_SUPPLIER_SWOT",
    ),
}


class DocumentService:
    async def assemble_context(
        self,
        template_key: str,
        context_id: str,
        *,
        session: AsyncSession,
        principal: Principal,
    ) -> dict:
        """Pull the exact (code-computed, RBAC-scoped) facts the template needs."""
        tpl = TEMPLATES[template_key]
        if tpl.context_kind == "opportunity":
            return await self._opportunity_context(session, principal, context_id)
        if tpl.context_kind == "contract":
            return await self._contract_context(session, principal, context_id)
        return await self._vendor_context(session, principal, context_id)

    async def _opportunity_context(self, session, principal, opp_id: str) -> dict:
        row = await session.execute(
            text(
                """
                SELECT o.id, o.type, o.bucket, o.impact, o.confidence, o.evidence,
                       c.id AS contract_id, v.name AS vendor_name, c.acv, c.end_date,
                       c.uplift_pct, c.renewal_notice_days
                FROM opportunities o
                LEFT JOIN contracts c ON o.contract_id = c.id
                LEFT JOIN vendors  v ON c.vendor_id = v.id
                WHERE o.id = CAST(:oid AS uuid)
                """
            ),
            {"oid": opp_id},
        )
        m = row.mappings().first()
        if m is None:
            raise DocumentNotAuthorizedError("opportunity not found or not authorized")
        return {k: _jsonable(v) for k, v in dict(m).items()}

    async def _contract_context(self, session, principal, contract_id: str) -> dict:
        row = await session.execute(
            text(
                """SELECT c.id, v.name AS vendor_name, c.acv, c.tcv, c.start_date,
                          c.end_date, c.renewal_type, c.renewal_notice_days, c.uplift_pct
                   FROM contracts c JOIN vendors v ON c.vendor_id = v.id
                   WHERE c.id = CAST(:cid AS uuid)"""
            ),
            {"cid": contract_id},
        )
        m = row.mappings().first()
        if m is None:
            raise DocumentNotAuthorizedError("contract not found or not authorized")
        return {k: _jsonable(v) for k, v in dict(m).items()}

    async def _vendor_context(self, session, principal, vendor_id: str) -> dict:
        row = await session.execute(
            text(
                """
                SELECT v.id, v.name AS vendor_name,
                       COUNT(DISTINCT c.id)        AS contract_count,
                       COALESCE(SUM(s.amount), 0)  AS total_spend,
                       COALESCE(SUM(c.acv), 0)     AS total_acv
                FROM vendors v
                LEFT JOIN contracts c     ON c.vendor_id = v.id
                LEFT JOIN spend_records s ON s.vendor_id = v.id
                WHERE v.id = CAST(:vid AS uuid)
                GROUP BY v.id, v.name
                """
            ),
            {"vid": vendor_id},
        )
        m = row.mappings().first()
        if m is None:
            raise DocumentNotAuthorizedError("vendor not found or not authorized")
        return {k: _jsonable(v) for k, v in dict(m).items()}


def _jsonable(v):
    """Coerce Decimals/dates/UUIDs to JSON-friendly strings for prompt + citation use."""
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID

    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


document_service = DocumentService()
