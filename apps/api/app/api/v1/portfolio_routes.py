"""Portfolio module API (§6.3, §8) — multi-entity rollup + Phase 10 governance
(consolidation, same-vendor multi-entity leverage, per-entity P&L). RBAC: portfolio_admin/admin."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.schemas.advanced import EntityRollupOut, PortfolioResponse
from app.services.portfolio import NotAuthorized, PortfolioGovernanceService, portfolio_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _today_month() -> date:
    """Default rollup period — the current month (callers may override via ?period=)."""
    from datetime import UTC, datetime

    return datetime.now(UTC).date().replace(day=1)


@router.get(
    "/by-entity",
    response_model=PortfolioResponse,
    dependencies=[Depends(require_permission("portfolio:read"))],
)
async def by_entity(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> PortfolioResponse:
    try:
        rows = await portfolio_service.by_entity(session, principal)
    except NotAuthorized as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return PortfolioResponse(entities=[EntityRollupOut(**r.__dict__) for r in rows])


@router.get("/consolidation", dependencies=[Depends(require_permission("portfolio:read"))])
async def consolidation(
    period: date | None = None,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = PortfolioGovernanceService(session, principal.tenant_id)
    try:
        return await svc.consolidate_spend(principal, period or _today_month())
    except NotAuthorized as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


@router.get("/vendor-leverage", dependencies=[Depends(require_permission("portfolio:read"))])
async def vendor_leverage(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = PortfolioGovernanceService(session, principal.tenant_id)
    try:
        return {"vendors": await svc.detect_vendor_leverage(principal)}
    except NotAuthorized as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


@router.get("/pnl-impact", dependencies=[Depends(require_permission("portfolio:read"))])
async def pnl_impact(
    period: date | None = None,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = PortfolioGovernanceService(session, principal.tenant_id)
    try:
        return {"entities": await svc.per_entity_pnl_impact(principal, period or _today_month())}
    except NotAuthorized as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
