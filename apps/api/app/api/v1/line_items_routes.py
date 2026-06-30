"""Line-item ingestion, line-item detection run, and recovery packs (§6.2, §6.3)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.invoice import InvoiceLineItem
from app.models.opportunity import Opportunity, RecoveryItem, RecoveryPack
from app.schemas.line_item import InboundInvoiceLineItem
from app.services.sku_normalization import sku_normalization_service

router = APIRouter(tags=["line-items"])


@router.post(
    "/invoices/{invoice_id}/line-items",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("data_quality:write"))],
)
async def ingest_line_items(
    invoice_id: str,
    body: list[InboundInvoiceLineItem],
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    inserted = 0
    for row in body:
        canonical = await sku_normalization_service.canonicalize(
            principal.tenant_id, row.sku or "", row.description
        )
        session.add(
            InvoiceLineItem(
                id=uuid4(),
                tenant_id=UUID(principal.tenant_id),
                invoice_id=UUID(invoice_id),
                line_number=row.line_number,
                sku=canonical if row.sku else None,
                raw_sku=row.sku,
                description=row.description,
                unit_price=row.unit_price,
                quantity=row.quantity,
                uom=row.uom,
                line_total=(row.unit_price * row.quantity),
                currency=row.currency,
            )
        )
        inserted += 1
    await session.commit()
    return {"invoice_id": invoice_id, "inserted": inserted}


@router.get(
    "/invoices/{invoice_id}/line-items",
    dependencies=[Depends(require_permission("data_quality:read"))],
)
async def list_line_items(invoice_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.scalars(
            select(InvoiceLineItem)
            .where(InvoiceLineItem.invoice_id == UUID(invoice_id))
            .order_by(InvoiceLineItem.line_number)
        )
    ).all()
    return {
        "invoice_id": invoice_id,
        "line_items": [
            {
                "id": str(li.id),
                "line_number": li.line_number,
                "sku": li.sku,
                "raw_sku": li.raw_sku,
                "unit_price": str(li.unit_price) if li.unit_price else None,
                "quantity": str(li.quantity) if li.quantity else None,
                "uom": li.uom,
            }
            for li in rows
        ],
    }


@router.post(
    "/detection/run-line-item",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("opportunity:read"))],
)
async def run_line_item_detection(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from app.services.line_item_detection import LineItemDetectionService

    opps = await LineItemDetectionService(session).run(principal.tenant_id)
    total = sum((o.impact for o in opps if o.counts_in_total), Decimal("0"))
    return {
        "detected": len(opps),
        "total_impact": str(total),
        "requires_rate_card_data": sum(1 for o in opps if o.status == "requires_rate_card_data"),
    }


@router.get(
    "/opportunities/{opp_id}/line-items",
    dependencies=[Depends(require_permission("opportunity:read"))],
)
async def opportunity_line_items(opp_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    opp = await session.get(Opportunity, UUID(opp_id))
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "opportunity not found")
    lines = opp.evidence.get("line_overcharges") or opp.evidence.get("lines") or []
    return {
        "opportunity_id": opp_id,
        "type": opp.type,
        "granularity": opp.granularity,
        "impact": str(opp.impact),
        "lines": lines,
    }


@router.post(
    "/recovery/packs/build",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("recovery:write"))],
)
async def build_recovery_pack(
    vendor_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from app.services.recovery_pack import recovery_pack_builder

    opps = (
        await session.scalars(
            select(Opportunity)
            .where(Opportunity.vendor_id == UUID(vendor_id))
            .where(Opportunity.bucket == "recovery")
        )
    ).all()
    pack = await recovery_pack_builder.build_for_vendor(
        principal.tenant_id, vendor_id, list(opps), session
    )
    await session.commit()
    return {"pack_id": str(pack.id), "vendor_id": vendor_id, "total_amount": str(pack.total_amount)}


@router.get(
    "/recovery/packs/{pack_id}",
    dependencies=[Depends(require_permission("recovery:read"))],
)
async def get_recovery_pack(pack_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    pack = await session.get(RecoveryPack, UUID(pack_id))
    if pack is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recovery pack not found")
    items = (
        await session.scalars(select(RecoveryItem).where(RecoveryItem.pack_id == pack.id))
    ).all()
    return {
        "pack_id": str(pack.id),
        "vendor_id": str(pack.vendor_id) if pack.vendor_id else None,
        "status": pack.status,
        "total_amount": str(pack.total_amount),
        "items": [
            {
                "id": str(it.id),
                "opp_type": (it.evidence or {}).get("opp_type"),
                "sku": it.sku,
                "quantity": str(it.quantity) if it.quantity is not None else None,
                "billed_rate": str(it.billed_rate) if it.billed_rate is not None else None,
                "contracted_rate": str(it.contracted_rate)
                if it.contracted_rate is not None
                else None,
                "line_delta": str(it.line_delta) if it.line_delta is not None else None,
                "amount": str(it.amount),
            }
            for it in items
        ],
    }
