"""Cost Intelligence API (single workspace, Sheets-driven). Data-source connect/test/refresh
plus the memory snapshot that powers every UI view. No tenant/auth gate — one workspace.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.cost_intelligence.service import CostIntelligenceService
from app.cost_intelligence.sheet_reader import SheetReadError

router = APIRouter(prefix="/ci", tags=["cost-intelligence"])


class ConnectBody(BaseModel):
    url: str
    name: str | None = None


class AskBody(BaseModel):
    question: str


@router.get("/data-source")
async def get_data_source(session: AsyncSession = Depends(get_session)) -> dict:
    """Connected spreadsheet config + sync status (powers Settings → Data Source)."""
    svc = CostIntelligenceService(session)
    s = await svc.status()
    s["default_spreadsheet_url"] = settings.ci_default_spreadsheet_url
    return s


@router.post("/data-source/test")
async def test_connection(
    body: ConnectBody, session: AsyncSession = Depends(get_session)
) -> dict:
    svc = CostIntelligenceService(session)
    try:
        return await svc.test_connection(body.url)
    except SheetReadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/data-source/connect")
async def connect(body: ConnectBody, session: AsyncSession = Depends(get_session)) -> dict:
    svc = CostIntelligenceService(session)
    try:
        result = await svc.connect(body.url, body.name)
    except SheetReadError as exc:
        await session.commit()  # persist the error marker
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return result


@router.post("/data-source/refresh")
async def refresh(session: AsyncSession = Depends(get_session)) -> dict:
    svc = CostIntelligenceService(session)
    try:
        result = await svc.refresh()
    except SheetReadError as exc:
        await session.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return result


@router.get("/snapshot")
async def snapshot(session: AsyncSession = Depends(get_session)) -> dict:
    """The full Agent Memory snapshot (normalized dataset + relationships + opportunities +
    KPIs). The UI slices this client-side, exactly like the prototype."""
    svc = CostIntelligenceService(session)
    snap = await svc.snapshot()
    if snap is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no data in memory — connect a spreadsheet first"
        )
    return snap


@router.post("/nirvana/ask")
async def nirvana_ask(body: AskBody, session: AsyncSession = Depends(get_session)) -> dict:
    """NirvanAI conversational Q&A grounded in Agent Memory (LLM-phrased when configured, else
    deterministic). Money is never computed by the LLM — answers quote memory figures only."""
    from app.cost_intelligence import nirvana

    svc = CostIntelligenceService(session)
    snap = await svc.snapshot()
    if snap is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no data in memory — connect a spreadsheet first"
        )
    return await nirvana.answer(snap, body.question)
