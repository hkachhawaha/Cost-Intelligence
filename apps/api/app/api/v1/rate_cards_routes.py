"""Rate cards API (§6.1) — CRUD, extraction, and the HITL verification gate.

Only verified cards (`verified_at IS NOT NULL`) drive line-item $ math. Verification is
role-gated (legal/category_mgr/admin) and audited."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit_event
from app.core.auth import Principal, get_current_principal
from app.core.config import settings
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.contract import Contract
from app.models.rate_card import ContractRateCard, RateCardTier
from app.schemas.line_item import ExtractedRateCardEntry

router = APIRouter(tags=["rate-cards"])
_READ = Depends(require_permission("contract:read"))
_WRITE = Depends(require_permission("contract:write"))


def _card_out(c: ContractRateCard) -> dict:
    return {
        "id": str(c.id),
        "sku": c.sku,
        "raw_sku": c.raw_sku,
        "description": c.description,
        "unit_rate": str(c.unit_rate),
        "uom": c.uom,
        "currency": c.currency,
        "is_tiered": c.is_tiered,
        "source": c.source,
        "confidence": str(c.confidence) if c.confidence is not None else None,
        "verified_at": c.verified_at.isoformat() if c.verified_at else None,
        "contract_id": str(c.contract_id),
        "tiers": [
            {
                "tier_index": t.tier_index,
                "min_volume": str(t.min_volume),
                "max_volume": str(t.max_volume) if t.max_volume is not None else None,
                "tier_rate": str(t.tier_rate),
            }
            for t in sorted(c.tiers, key=lambda x: x.tier_index)
        ],
    }


async def _get_card(session: AsyncSession, card_id: str) -> ContractRateCard:
    card = await session.scalar(
        select(ContractRateCard)
        .where(ContractRateCard.id == UUID(card_id))
        .options(selectinload(ContractRateCard.tiers))
    )
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rate card not found")
    return card


@router.get("/contracts/{contract_id}/rate-cards", dependencies=[_READ])
async def list_rate_cards(contract_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    cards = (
        await session.scalars(
            select(ContractRateCard)
            .where(ContractRateCard.contract_id == UUID(contract_id))
            .options(selectinload(ContractRateCard.tiers))
        )
    ).all()
    return {"contract_id": contract_id, "rate_cards": [_card_out(c) for c in cards]}


@router.post(
    "/contracts/{contract_id}/rate-cards",
    status_code=status.HTTP_201_CREATED,
    dependencies=[_WRITE],
)
async def create_rate_card(
    contract_id: str,
    body: ExtractedRateCardEntry,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if await session.get(Contract, UUID(contract_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contract not found")
    card = ContractRateCard(
        id=uuid4(),
        tenant_id=UUID(principal.tenant_id),
        contract_id=UUID(contract_id),
        sku=body.sku,
        raw_sku=body.sku,
        description=body.description,
        unit_rate=body.unit_rate if body.unit_rate is not None else 0,
        uom=body.uom,
        is_tiered=body.is_tiered,
        source="manual",
        confidence=body.confidence,
    )
    session.add(card)
    await session.flush()
    for i, tier in enumerate(body.tiers):
        session.add(
            RateCardTier(
                id=uuid4(),
                tenant_id=UUID(principal.tenant_id),
                rate_card_id=card.id,
                tier_index=i,
                min_volume=tier.min_volume,
                max_volume=tier.max_volume,
                tier_rate=tier.tier_rate,
            )
        )
    await session.commit()
    return await _card_out_reload(session, card.id)


async def _card_out_reload(session: AsyncSession, card_id: UUID) -> dict:
    return _card_out(await _get_card(session, str(card_id)))


@router.post("/extract/contracts/{contract_id}/rate-cards", dependencies=[_WRITE])
async def extract_rate_cards(
    contract_id: str,
    body: dict,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Run sandboxed rate-card extraction over (untrusted) contract text → staged unverified."""
    from app.core.agent_run import agent_run
    from app.services.rate_card_extraction import RateCardExtractionService

    if await session.get(Contract, UUID(contract_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contract not found")
    async with agent_run(
        tenant_id=principal.tenant_id, agent="rate_card_extraction", trigger="user_request"
    ) as run:
        svc = RateCardExtractionService(session)
        summary = await svc.extract_and_stage(
            principal.tenant_id, contract_id, body.get("contract_text", ""), run_id=str(run.run_id)
        )
        run.set_outputs(summary)
    return summary


@router.get("/rate-cards/verification-queue", dependencies=[_READ])
async def verification_queue(session: AsyncSession = Depends(get_session)) -> dict:
    cards = (
        await session.scalars(
            select(ContractRateCard)
            .where(ContractRateCard.verified_at.is_(None))
            .order_by(desc(ContractRateCard.created_at))
            .options(selectinload(ContractRateCard.tiers))
        )
    ).all()
    return {"items": [_card_out(c) for c in cards]}


@router.post("/rate-cards/{card_id}/verify", dependencies=[_WRITE])
async def verify_rate_card(
    card_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if principal.role not in settings.rate_card_verify_roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "verify requires legal/category_mgr/admin")
    card = await _get_card(session, card_id)
    if card.verified_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "rate card already verified")
    card.verified_by = UUID(principal.user_id)
    card.verified_at = datetime.now(UTC)
    await record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        event_type="rate_card.verified",
        actor="human",
        actor_user_id=UUID(principal.user_id),
        payload={"rate_card_id": card_id, "sku": card.sku},
        run_id=card.extraction_run_id,
    )
    await session.commit()
    return {
        "id": card_id,
        "verified_by": principal.user_id,
        "verified_at": card.verified_at.isoformat(),
        "status": "verified",
    }


@router.delete("/rate-cards/{card_id}", dependencies=[_WRITE])
async def delete_rate_card(card_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    card = await _get_card(session, card_id)
    await session.delete(card)
    await session.commit()
    return {"id": card_id, "deleted": True}


@router.get("/rate-cards/{card_id}", dependencies=[_READ])
async def get_rate_card(card_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return _card_out(await _get_card(session, card_id))


@router.patch("/rate-cards/{card_id}", dependencies=[_WRITE])
async def patch_rate_card(
    card_id: str, body: dict, session: AsyncSession = Depends(get_session)
) -> dict:
    card = await _get_card(session, card_id)
    if "unit_rate" in body:
        card.unit_rate = body["unit_rate"]
    if "description" in body:
        card.description = body["description"]
    if "uom" in body:
        card.uom = body["uom"]
    await session.commit()
    return _card_out(card)


@router.get("/rate-cards", dependencies=[_READ])
async def list_all_rate_cards(
    contract_id: str | None = Query(None), session: AsyncSession = Depends(get_session)
) -> dict:
    q = select(ContractRateCard).options(selectinload(ContractRateCard.tiers))
    if contract_id:
        q = q.where(ContractRateCard.contract_id == UUID(contract_id))
    cards = (await session.scalars(q.order_by(desc(ContractRateCard.created_at)))).all()
    return {"rate_cards": [_card_out(c) for c in cards]}
