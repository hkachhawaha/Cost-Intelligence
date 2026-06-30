"""Cost Intelligence end-to-end scenarios (realignment Phase 4) — live Postgres, migration 011.

Maps 1:1 to the validation scenarios: spreadsheet connection, initial sync, refresh,
Contract↔Invoice / Invoice↔Spend / Contract↔Spend-fallback matching, dashboard data contract,
insight generation, NirvanAI data contract, and error handling. The sheet read is monkeypatched
to a rich in-memory workbook (no network) that triggers every relationship type and insight.

Run: RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_ci_e2e_scenarios.py -v
"""

from __future__ import annotations

import asyncio
import io

import pytest

from tests.conftest import requires_db

pytestmark = requires_db

_AS_OF = "2025-07-01"
_URL = "https://docs.google.com/spreadsheets/d/E2EFIXTURE000000000000000/edit"


def _xlsx() -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    def tab(name, header, rows):
        ws = wb.create_sheet(name)
        ws.append([f"{name} — banner"])  # row 1 banner
        ws.append(header)  # row 2 header
        for r in rows:
            ws.append(r)

    tab(
        "Contracts",
        [
            "Contract_ID",
            "Vendor_Name",
            "Category",
            "Region",
            "Annual_Value_USD",
            "Contract_Value_USD",
            "Effective_Date",
            "Expiration_Date",
            "Renewal_Notice_Days",
            "Auto_Renew",
            "Rebate_Clause",
            "SLA_Penalty_Clause",
            "Volume_Commitment",
            "Payment_Terms",
            "Contract_Status",
            "Department",
        ],
        [
            [
                "NXC-1",
                "Acme Cloud",
                "Cloud & Infrastructure",
                "Global",
                200000,
                600000,
                "2024-07-01",
                "2025-07-15",
                30,
                "Y",
                "Y",
                "N",
                "$300K/year",
                "Net-30",
                "Active",
                "IT",
            ],
            [
                "NXC-2",
                "Globex Telecom",
                "Telecom",
                "EU",
                100000,
                200000,
                "2023-01-01",
                "2025-01-01",
                60,
                "N",
                "N",
                "N",
                "None",
                "Net-30",
                "Active",
                "Network",
            ],
        ],
    )
    tab(
        "Contract Clauses",
        [
            "Contract_ID",
            "Vendor_Name",
            "Clause_Type",
            "Clause_Summary",
            "Key_Threshold",
            "Claim_Window",
        ],
        [
            [
                "NXC-1",
                "Acme Cloud",
                "Rebate",
                "Annual spend rebate: 2% of fees if annual spend exceeds $150K.",
                "$150K annual spend",
                "Q1 following year",
            ],
            [
                "NXC-1",
                "Acme Cloud",
                "Pricing_Schedule",
                "Rates: Consultant $150, Senior $180 per hour.",
                "$180/hr Senior",
                "30 days",
            ],
        ],
    )
    tab(
        "Invoices",
        [
            "Invoice_ID",
            "Vendor_Name",
            "Contract_ID",
            "PO_Number",
            "Invoice_Date",
            "Unit_Price_Billed",
            "Quantity",
            "Amount_Billed_USD",
            "Payment_Status",
        ],
        [
            ["INV-1", "Acme Cloud", "NXC-1", "PO-1", "2025-03-01", 200, 100, 20000, "Paid"],
            ["INV-2", "Acme Cloud", "NXC-1", "PO-1", "2025-04-01", 180, 50, 9000, "Paid"],
        ],
    )
    tab(
        "Purchase Orders",
        ["PO_Number", "Vendor_Name", "Contract_ID", "PO_Amount_USD", "PO_Status"],
        [
            ["PO-1", "Acme Cloud", "NXC-1", 168000, "Closed"],
            ["PO-2", "Acme Cloud", "NXC-1", 50000, "Open"],
        ],
    )
    tab(
        "Inventory",
        [
            "Asset_ID",
            "Vendor_Name",
            "Contract_ID",
            "Product_Name",
            "Qty_Licensed",
            "Qty_Active_90d",
            "Annual_Cost_USD",
            "Asset_Status",
        ],
        [["AST-1", "Acme Cloud", "NXC-1", "Seat", 100, 50, 120, "Active"]],
    )
    tab(
        "Spend Ledger",
        [
            "Transaction_ID",
            "Transaction_Date",
            "Vendor_Name",
            "Contract_ID",
            "PO_Number",
            "Cost_Center",
            "GL_Account",
            "Amount_USD",
            "Invoice_Reference",
        ],
        [
            ["TXN-1", "2025-03-01", "Acme Cloud", "NXC-1", "PO-1", "CC-1", "GL-1", 260000, "INV-1"],
            ["TXN-D1", "2025-03-02", "Acme Cloud", "NXC-1", "PO-1", "CC-1", "GL-1", 5000, "DUP"],
            ["TXN-D2", "2025-03-03", "Acme Cloud", "NXC-1", "PO-1", "CC-1", "GL-1", 5000, "DUP"],
            ["TXN-PO", "2025-03-04", "Acme Cloud", "", "PO-2", "CC-1", "GL-1", 1000, "INV-X"],
            ["TXN-VEN", "2025-03-05", "Acme Cloud", "", "", "CC-1", "GL-1", 2000, "INV-Y"],
            ["TXN-EXP", "2025-03-06", "Globex Telecom", "NXC-2", "", "CC-2", "GL-2", 8000, "INV-Z"],
            ["TXN-MAV", "2025-03-07", "Rogue Vendor Ltd", "", "", "CC-9", "GL-9", 50000, "INV-M"],
        ],
    )
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _dsn() -> str:
    from app.core.config import settings

    return settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")


def _truncate():
    import psycopg

    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE ci_memory_snapshot, ci_data_source CASCADE")


@pytest.fixture()
def snap(monkeypatch):
    """Connect the fixture workbook once; yield the stored Agent Memory snapshot."""
    from app.core.config import settings
    from app.core.database import SessionFactory
    from app.cost_intelligence.service import CostIntelligenceService
    from app.cost_intelligence.sheet_reader import GoogleSheetReader

    monkeypatch.setattr(settings, "ci_as_of_date", _AS_OF)  # deterministic "today"

    async def _fake_fetch(self, sid):  # noqa: ANN001
        return _xlsx()

    monkeypatch.setattr(GoogleSheetReader, "fetch_xlsx", _fake_fetch)
    _truncate()

    async def run():
        async with SessionFactory() as s:
            svc = CostIntelligenceService(s)
            res = await svc.connect(_URL, "E2E Fixture")
            await s.commit()
            snapshot = await svc.snapshot()
            return res, snapshot

    res, snapshot = asyncio.run(run())
    yield {"res": res, "snap": snapshot}
    _truncate()


# 1) Spreadsheet connection + initial sync
def test_scenario_connect_initial_sync(snap):
    res = snap["res"]
    assert res["connected"] is True and res["status"] == "connected"
    assert res["memory_version"] == 1
    counts = snap["snap"]["relationships"]["counts"]
    assert counts["contracts"] == 2 and counts["spend"] == 7 and counts["invoices"] == 2


# 2) Contract ↔ Invoice matching
def test_scenario_contract_invoice_match(snap):
    rel = snap["snap"]["relationships"]
    assert rel["contractToInvoiceCount"].get("NXC-1") == 2


# 3) Invoice ↔ Spend matching (spend.Invoice_Reference → invoice id)
def test_scenario_invoice_spend_match(snap):
    rel = snap["snap"]["relationships"]
    assert rel["invoiceSpendLinks"] >= 1  # TXN-1.invoiceRef == INV-1


# 4) Contract ↔ Spend fallback (no Contract_ID → PO, then vendor)
def test_scenario_contract_spend_fallback(snap):
    by_id = {s["id"]: s for s in snap["snap"]["spend"]}
    assert (
        by_id["TXN-PO"]["matchMethod"] == "PO" and by_id["TXN-PO"]["resolvedContractId"] == "NXC-1"
    )
    assert by_id["TXN-VEN"]["matchMethod"] == "Vendor (exact)"
    assert by_id["TXN-MAV"]["resolvedContractId"] is None  # maverick


# 5) Insight generation — every supported rule fires from this fixture
def test_scenario_insight_generation(snap):
    types = {o["type"] for o in snap["snap"]["opportunities"]}
    for expected in [
        "Overspend vs ACV",
        "Duplicate invoice",
        "Maverick spend",
        "Silent auto-renewal",
        "Spend after expiry",
        "Unclaimed rebate",
        "Off-rate billing",
        "License shelfware",
    ]:
        assert expected in types, f"missing insight: {expected}"


# 6) Dashboard data contract — KPIs present and internally consistent
def test_scenario_dashboard_data_contract(snap):
    k = snap["snap"]["kpis"]
    for key in (
        "total",
        "matched",
        "identified",
        "recoverable",
        "savings",
        "oppCount",
        "spendUnderMgmtPct",
        "poCoveragePct",
    ):
        assert key in k
    opps = snap["snap"]["opportunities"]
    assert round(k["identified"], 2) == round(sum(o["impact"] for o in opps), 2)
    assert round(k["recoverable"] + k["savings"], 2) == round(k["identified"], 2)
    assert k["total"] == 331000.0  # Σ spend amounts


# 7) NirvanAI data contract — memory holds what the assistant answers from
def test_scenario_nirvana_data_contract(snap):
    s = snap["snap"]
    assert len(s["contracts"]) and len(s["opportunities"])
    # Recoverable-now answer is derivable; top opportunity has a vendor subject for doc gen.
    assert s["kpis"]["recoverable"] > 0
    assert any(o.get("subject") for o in s["opportunities"])


# 8) Refresh process — re-read rebuilds a new memory version
def test_scenario_refresh_rebuilds(monkeypatch):
    from app.core.config import settings
    from app.core.database import SessionFactory
    from app.cost_intelligence.service import CostIntelligenceService
    from app.cost_intelligence.sheet_reader import GoogleSheetReader

    monkeypatch.setattr(settings, "ci_as_of_date", _AS_OF)

    async def _fake_fetch(self, sid):  # noqa: ANN001
        return _xlsx()

    monkeypatch.setattr(GoogleSheetReader, "fetch_xlsx", _fake_fetch)
    _truncate()

    async def run():
        async with SessionFactory() as s:
            svc = CostIntelligenceService(s)
            await svc.connect(_URL, "E2E Fixture")
            await s.commit()
            r2 = await svc.refresh()
            await s.commit()
            return r2

    try:
        r2 = asyncio.run(run())
        assert r2["memory_version"] == 2
    finally:
        _truncate()


# 9) Error handling — an unreachable / non-public sheet is reported, not crashed
def test_scenario_error_handling(monkeypatch):
    from app.core.database import SessionFactory
    from app.cost_intelligence.service import CostIntelligenceService
    from app.cost_intelligence.sheet_reader import GoogleSheetReader, SheetReadError

    async def _boom(self, sid):  # noqa: ANN001
        raise SheetReadError("could not fetch workbook (HTTP 403); is the sheet shared?")

    monkeypatch.setattr(GoogleSheetReader, "fetch_xlsx", _boom)
    _truncate()

    async def run():
        async with SessionFactory() as s:
            svc = CostIntelligenceService(s)
            raised = False
            try:
                await svc.connect(_URL, "Bad")
            except SheetReadError:
                raised = True
            await s.commit()
            status = await svc.status()
            return raised, status

    try:
        raised, status = asyncio.run(run())
        assert raised is True
        assert status["status"] == "error" and status["last_error"]
    finally:
        _truncate()


# 10) HTTP API end-to-end — connect via the real route, then read the snapshot
def test_scenario_http_connect_and_snapshot(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core import auth as auth_mod
    from app.core.config import settings
    from app.core.database import SessionFactory, get_session
    from app.cost_intelligence.sheet_reader import GoogleSheetReader
    from app.main import app

    monkeypatch.setattr(settings, "ci_as_of_date", _AS_OF)

    async def _fake_fetch(self, sid):  # noqa: ANN001
        return _xlsx()

    monkeypatch.setattr(GoogleSheetReader, "fetch_xlsx", _fake_fetch)

    async def _noop():
        return None

    monkeypatch.setattr(auth_mod.jwks_cache, "_refresh", _noop)

    async def _session():
        s = SessionFactory()
        try:
            yield s
            await s.commit()
        finally:
            await s.close()

    app.dependency_overrides[get_session] = _session
    _truncate()
    client = TestClient(app)
    try:
        r = client.post("/api/v1/ci/data-source/connect", json={"url": _URL, "name": "E2E HTTP"})
        assert r.status_code == 200 and r.json()["connected"] is True
        snap = client.get("/api/v1/ci/snapshot").json()
        assert snap["kpis"]["oppCount"] >= 6
        assert {o["type"] for o in snap["opportunities"]} >= {"Overspend vs ACV", "Maverick spend"}
    finally:
        app.dependency_overrides.clear()
        _truncate()


# 11) HTTP API error path — a bad sheet returns 400, never a 500
def test_scenario_http_error_returns_400(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core import auth as auth_mod
    from app.core.database import SessionFactory, get_session
    from app.cost_intelligence.sheet_reader import GoogleSheetReader, SheetReadError
    from app.main import app

    async def _boom(self, sid):  # noqa: ANN001
        raise SheetReadError("could not fetch workbook (HTTP 403)")

    async def _noop():
        return None

    monkeypatch.setattr(GoogleSheetReader, "fetch_xlsx", _boom)
    monkeypatch.setattr(auth_mod.jwks_cache, "_refresh", _noop)

    async def _session():
        s = SessionFactory()
        try:
            yield s
            await s.commit()
        finally:
            await s.close()

    app.dependency_overrides[get_session] = _session
    _truncate()
    client = TestClient(app)
    try:
        r = client.post("/api/v1/ci/data-source/connect", json={"url": _URL, "name": "Bad"})
        assert r.status_code == 400  # clean domain error, not a crash
    finally:
        app.dependency_overrides.clear()
        _truncate()
