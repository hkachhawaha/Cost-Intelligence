"""Cost Intelligence API (single workspace, Sheets-driven). Data-source connect/test/refresh
plus the memory snapshot that powers every UI view. No tenant/auth gate — one workspace.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.core.database import get_session
from app.cost_intelligence.service import CostIntelligenceService
from app.cost_intelligence.sheet_reader import SheetReadError

router = APIRouter(prefix="/ci", tags=["cost-intelligence"])
log = structlog.get_logger()


class ConnectBody(BaseModel):
    url: str
    name: str | None = None


class AskBody(BaseModel):
    question: str


@router.get("/data-source")
async def get_data_source(session: AsyncSession = Depends(get_session)) -> dict:
    """Connected spreadsheet config + sync status (powers Settings → Data Source)."""
    log.info("ci.get_data_source.start")
    svc = CostIntelligenceService(session)
    s = await svc.status()
    s["default_spreadsheet_url"] = settings.ci_default_spreadsheet_url
    log.info("ci.get_data_source.completed", status=s.get("status"), total_records=s.get("total_records"))
    return s


@router.post("/data-source/test")
async def test_connection(
    body: ConnectBody, session: AsyncSession = Depends(get_session)
) -> dict:
    log.info("ci.test_connection.start", url=body.url)
    svc = CostIntelligenceService(session)
    try:
        res = await svc.test_connection(body.url)
        log.info("ci.test_connection.success", url=body.url, total_rows=res.get("total_rows"))
        return res
    except SheetReadError as exc:
        log.error("ci.test_connection.failed", url=body.url, error=str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/data-source/connect")
async def connect(body: ConnectBody, session: AsyncSession = Depends(get_session)) -> dict:
    log.info("ci.connect.start", url=body.url, name=body.name)
    svc = CostIntelligenceService(session)
    try:
        result = await svc.connect(body.url, body.name)
        log.info("ci.connect.success", url=body.url, name=body.name, records=result.get("total_records"))
    except SheetReadError as exc:
        log.error("ci.connect.failed", url=body.url, error=str(exc))
        await session.commit()  # persist the error marker
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return result


@router.post("/data-source/refresh")
async def refresh(session: AsyncSession = Depends(get_session)) -> dict:
    log.info("ci.refresh.start")
    svc = CostIntelligenceService(session)
    try:
        result = await svc.refresh()
        log.info("ci.refresh.success", url=result.get("spreadsheet_url"), records=result.get("total_records"))
    except SheetReadError as exc:
        log.error("ci.refresh.failed", error=str(exc))
        await session.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return result


@router.get("/snapshot")
async def snapshot(session: AsyncSession = Depends(get_session)) -> dict:
    """The full Agent Memory snapshot (normalized dataset + relationships + opportunities +
    KPIs). The UI slices this client-side, exactly like the prototype."""
    log.info("ci.snapshot.start")
    svc = CostIntelligenceService(session)
    snap = await svc.snapshot()
    if snap is None:
        log.warning("ci.snapshot.not_found")
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no data in memory — connect a spreadsheet first"
        )
    log.info("ci.snapshot.success", version=snap.get("version"))
    return snap


@router.post("/nirvana/ask")
async def ask(body: AskBody, session: AsyncSession = Depends(get_session)) -> dict:
    """NirvanAI conversational Q&A grounded in Agent Memory (LLM-phrased when configured, else
    deterministic). Money is never computed by the LLM — answers quote memory figures only."""
    log.info("ci.ask.start", question=body.question)
    from app.cost_intelligence import nirvana

    svc = CostIntelligenceService(session)
    snap = await svc.snapshot()
    if snap is None:
        log.warning("ci.ask.no_snapshot")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Run an initial sync to enable NirvanaI."
        )
    try:
        res = await nirvana.answer(snap, body.question)
        log.info("ci.ask.success", question=body.question)
        return res
    except Exception as exc:  # noqa: BLE001 — advisory fallback
        log.error("ci.ask.failed", question=body.question, error=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc


@router.get("/settings/llm-providers")
async def get_llm_providers() -> dict:
    """Get the active LLM provider configuration and model mapping details."""
    has_key = settings.gemini_api_key is not None and len(str(settings.gemini_api_key).strip()) > 0
    return {
        "providers": [
            {
                "name": "Google Gemini",
                "active": has_key,
                "status": "connected" if has_key else "missing key",
                "models": [
                    {
                        "alias": "complex",
                        "model": "gemini-2.5-pro",
                        "useCase": "Generative drafting & conversation",
                        "costPerMillion": {"input": "$1.25", "output": "$10.00"}
                    },
                    {
                        "alias": "fast",
                        "model": "gemini-2.5-flash",
                        "useCase": "Intent routing & classification",
                        "costPerMillion": {"input": "$0.30", "output": "$2.50"}
                    }
                ]
            }
        ]
    }
