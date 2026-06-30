"""Cost Intelligence unit tests (realignment) — no DB, no network.

Cover the ingestion reader (banner skip, Read Me skip, blank-key truncation), schema mapping
+ commitment parsing, the relationship resolution ladder + the three linkages, the deterministic
insight rules (all grounded in the Nexus shape), and KPI consistency.
"""

from __future__ import annotations

import io

from app.cost_intelligence.insights import compute_kpis, generate_opportunities
from app.cost_intelligence.mappers import map_contract, parse_commitment_to_annual
from app.cost_intelligence.relationships import build_relationships
from app.cost_intelligence.service import build_intelligence
from app.cost_intelligence.sheet_reader import parse_workbook


def _xlsx(tabs: dict[str, list[list]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in tabs.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


_CONTRACT_HDR = [
    "Contract_ID", "Vendor_Name", "Category", "Subcategory", "Region", "Contract_Value_USD",
    "Annual_Value_USD", "Effective_Date", "Expiration_Date", "Renewal_Notice_Days", "Auto_Renew",
    "Pricing_Model", "Payment_Terms", "Rebate_Clause", "SLA_Penalty_Clause", "Volume_Commitment",
    "Most_Recent_Amendment", "Internal_Owner", "Department", "Contract_Status",
]


# ── ingestion reader ──────────────────────────────────────────────────────────────
def test_parse_workbook_skips_banner_readme_and_blank_rows():
    data = _xlsx({
        "Read Me": [["NEXUS — cover"], ["scenario"]],
        "Contracts": [
            ["NEXUS — Contract Register (banner)"],  # row 1 banner (skipped)
            ["Contract_ID", "Vendor_Name", "Annual_Value_USD"],  # row 2 header
            ["NXC-1", "Acme Cloud", 240000],
            ["NXC-2", "Globex", 180000],
            [None, None, None],  # blank key → truncates here
            ["NXC-IGNORED", "ShouldNotAppear", 1],
        ],
    })
    parsed = parse_workbook(data)
    assert "Read Me" not in parsed  # cover tab never ingested
    assert [r["Contract_ID"] for r in parsed["Contracts"]] == ["NXC-1", "NXC-2"]
    assert parsed["Contracts"][0]["Vendor_Name"] == "Acme Cloud"


def test_parse_commitment_to_annual():
    assert parse_commitment_to_annual("$400K/quarter") == 1_600_000
    assert parse_commitment_to_annual("$55K/month") == 660_000
    assert parse_commitment_to_annual("$1.2M/year") == 1_200_000
    assert parse_commitment_to_annual("None") is None
    assert parse_commitment_to_annual("") is None


def test_map_contract_coerces_types():
    row = dict(zip(_CONTRACT_HDR, [
        "NXC-9", "Acme LLP", "Cloud", "CDN", "Global", 1000000, 500000, "2025-01-01",
        "2026-01-01", 90, "Y", "Consumption", "Net-45", "Y", "N", "$100K/month",
        "None", "J. Doe", "IT", "Active",
    ], strict=False))
    c = map_contract(row)
    assert c["id"] == "NXC-9" and c["acv"] == 500000.0
    assert c["autoRenew"] is True and c["renewalType"] == "Auto-renewal"
    assert c["rebateClause"] is True and c["slaPenaltyClause"] is False
    assert c["paymentTermDays"] == 45
    assert c["yearlyCommit"] == 1_200_000  # $100K/month × 12
    assert c["start"] == "2025-01-01" and c["end"] == "2026-01-01"


# ── relationship resolution ladder ─────────────────────────────────────────────────
def _dataset():
    return {
        "contracts": [
            {"id": "NXC-1", "vendor": "Acme Cloud Services", "acv": 200000, "end": "2026-01-01",
             "autoRenew": True, "renewalNoticeDays": 30, "status": "Active", "yearlyCommit": None},
            {"id": "NXC-2", "vendor": "Globex Telecom", "acv": 100000, "end": "2025-01-01",
             "autoRenew": False, "renewalNoticeDays": 60, "status": "Active",
             "yearlyCommit": 100000},
        ],
        "purchaseOrders": [{"poNumber": "PO-1", "contractId": "NXC-1"}],
        "invoices": [
            {"id": "INV-1", "contractId": "NXC-1", "unitPriceBilled": 200, "quantity": 10,
             "amount": 2000},
        ],
        "clauses": [
            {"contractId": "NXC-1", "clauseType": "Rebate", "summary": "2% rebate over threshold",
             "keyThreshold": "$150K annual spend", "claimWindow": "Q1"},
            {"contractId": "NXC-1", "clauseType": "Pricing_Schedule",
             "summary": "Rates: Consultant $150, Senior $180.", "keyThreshold": "$180/hr"},
        ],
        "inventory": [
            {"contractId": "NXC-1", "productName": "Seat", "vendor": "Acme Cloud Services",
             "qtyLicensed": 100, "qtyActive90d": 50, "idleQty": 50, "annualCost": 120},
            {"contractId": "NXC-1", "productName": "Seat", "vendor": "Acme Cloud Services",
             "qtyLicensed": 100, "qtyActive90d": 50, "idleQty": 50, "annualCost": 120},
        ],
        "spend": [
            {"id": "T1", "vendor": "Acme Cloud Services", "contractId": "NXC-1", "po": "PO-1",
             "amount": 260000, "spendDate": "2025-06-01", "invoiceRef": "INV-1"},  # over ACV
            {"id": "T2", "vendor": "Acme Cloud Services", "contractId": "NXC-1", "po": None,
             "amount": 5000, "spendDate": "2026-06-01", "invoiceRef": "INV-9"},  # post-expiry
            {"id": "T3", "vendor": "Globex Telecom", "contractId": None, "po": "PO-1",
             "amount": 1000, "spendDate": "2025-05-01", "invoiceRef": "DUP"},
            {"id": "T4", "vendor": "Globex Telecom", "contractId": None, "po": "PO-1",
             "amount": 1000, "spendDate": "2025-05-02", "invoiceRef": "DUP"},  # duplicate of T3
            {"id": "T5", "vendor": "Unknown Vendor XYZ", "contractId": None, "po": None,
             "amount": 9000, "spendDate": "2025-05-01", "invoiceRef": "M1"},  # maverick
        ],
    }


def test_relationship_resolution_and_linkages():
    ds = _dataset()
    rel = build_relationships(ds)
    by_id = {s["id"]: s for s in ds["spend"]}
    assert by_id["T1"]["matchMethod"] == "Contract ID" and by_id["T1"]["matchConfidence"] == 0.97
    assert by_id["T3"]["matchMethod"] == "PO"  # no contractId, resolves via PO register
    assert by_id["T5"]["resolvedContractId"] is None  # maverick
    assert rel["counts"]["maverickRecords"] == 1
    assert rel["contractToInvoiceCount"]["NXC-1"] == 1  # contract↔invoice
    assert rel["invoiceSpendLinks"] >= 1  # invoice↔spend (T1.invoiceRef == INV-1)


# ── insight rules ───────────────────────────────────────────────────────────────────
def test_insights_fire_expected_rules():
    ds = _dataset()
    rel = build_relationships(ds)
    opps = generate_opportunities(ds, rel)
    types = {o["type"] for o in opps}
    assert "Overspend vs ACV" in types  # T1 260k > 200k ACV
    assert "Spend after expiry" in types  # T2 after 2026-01-01
    assert "Duplicate invoice" in types  # T3/T4 same ref+amount
    assert "Maverick spend" in types  # T5
    assert "Silent auto-renewal" in types  # NXC-1 auto-renew in window
    assert "Unclaimed rebate" in types  # spend 265k > 150k threshold, 2%
    assert "License shelfware" in types  # 50/100 idle

    rebate = next(o for o in opps if o["type"] == "Unclaimed rebate")
    assert rebate["bucket"] == "recovery"
    # Shelfware deduped by product (max 100 licensed, not summed across the 2 rows).
    shelf = next(o for o in opps if o["type"] == "License shelfware")
    assert shelf["impact"] == 50 * 120  # 50 idle × $120, counted once


def test_kpis_consistent_with_opportunities():
    payload = build_intelligence({})  # empty → empty dataset path
    assert payload["kpis"]["total"] == 0.0 and payload["kpis"]["oppCount"] == 0

    ds = _dataset()
    rel = build_relationships(ds)
    opps = generate_opportunities(ds, rel)
    k = compute_kpis(ds, rel, opps)
    assert round(k["identified"], 2) == round(sum(o["impact"] for o in opps), 2)
    assert round(k["recoverable"] + k["savings"], 2) == round(k["identified"], 2)
    assert k["recordCounts"]["maverickRecords"] == 1
