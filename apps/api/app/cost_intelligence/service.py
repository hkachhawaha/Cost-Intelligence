"""CostIntelligenceService — orchestrates the data layer: connect/test/refresh and reads.

connect/refresh: read the workbook → map → build relationships → generate insights → compute
KPIs → store the snapshot in Agent Memory. The UI reads `snapshot()` (memory), never the sheet.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.cost_intelligence.insights import compute_kpis, generate_opportunities
from app.cost_intelligence.mappers import map_workbook
from app.cost_intelligence.memory import AgentMemory
from app.cost_intelligence.relationships import build_relationships
from app.cost_intelligence.sheet_reader import (
    GoogleSheetReader,
    SheetReadError,
    extract_spreadsheet_id,
)

logger = logging.getLogger("ci.service")


def build_intelligence(tabs: dict[str, list[dict]]) -> dict:
    """Pure pipeline: raw tabs → normalized dataset + relationships + opportunities + KPIs.
    Returns the snapshot payload (without memory metadata)."""
    dataset = map_workbook(tabs)
    rel = build_relationships(dataset)  # annotates spend in place
    opps = generate_opportunities(dataset, rel)
    kpis = compute_kpis(dataset, rel, opps)
    return {**dataset, "relationships": rel, "opportunities": opps, "kpis": kpis}


class CostIntelligenceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.reader = GoogleSheetReader()
        self.memory = AgentMemory(session)

    async def test_connection(self, url: str) -> dict:
        """Read the workbook WITHOUT storing — report reachability + per-tab row counts."""
        tabs = await self.reader.read(url)
        return {
            "ok": True,
            "spreadsheet_id": extract_spreadsheet_id(url),
            "tabs": {name: len(rows) for name, rows in tabs.items()},
            "total_rows": sum(len(r) for r in tabs.values()),
        }

    async def connect(self, url: str, name: str | None = None) -> dict:
        sid = extract_spreadsheet_id(url)
        try:
            tabs = await self.reader.read(url)
            payload = build_intelligence(tabs)
            version = await self.memory.store(
                spreadsheet_id=sid, url=url, name=name, payload=payload
            )
        except SheetReadError as exc:
            await self.memory.mark_error(spreadsheet_id=sid, url=url, error=str(exc))
            raise
        return await self._status_with(payload, version)

    async def refresh(self) -> dict:
        ds = await self.memory.data_source()
        if ds is None:
            raise SheetReadError("no spreadsheet connected — connect one first")
        return await self.connect(ds.spreadsheet_url, ds.spreadsheet_name)

    async def status(self) -> dict:
        ds = await self.memory.data_source()
        if ds is None:
            return {"connected": False, "status": "never"}
        return {
            "connected": ds.status == "connected",
            "status": ds.status,
            "spreadsheet_url": ds.spreadsheet_url,
            "spreadsheet_name": ds.spreadsheet_name,
            "last_synced_at": ds.last_synced_at.isoformat() if ds.last_synced_at else None,
            "total_records": ds.total_records,
            "last_error": ds.last_error,
        }

    async def snapshot(self) -> dict | None:
        return await self.memory.latest()

    async def _status_with(self, payload: dict, version: int) -> dict:
        base = await self.status()
        base["memory_version"] = version
        base["kpis"] = payload.get("kpis", {})
        base["opportunity_count"] = len(payload.get("opportunities", []))
        return base
