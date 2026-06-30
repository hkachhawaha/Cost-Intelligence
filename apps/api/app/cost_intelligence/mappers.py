"""Schema mapping (ingestion layer). Normalize each Nexus tab's raw rows into canonical,
JSON-serializable records with coerced types (ISO dates, numbers, Y/N → bool, parsed volume
commitments). Pure functions — unit-tested without network.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_K_PER = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
_PERIOD_PER_YEAR = {"month": 12, "mo": 12, "quarter": 4, "qtr": 4, "year": 1, "yr": 1, "annum": 1}


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[,$\s]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return None


def _int(v: Any) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


def _iso_date(v: Any) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, (datetime, date)):
        return v.date().isoformat() if isinstance(v, datetime) else v.isoformat()
    s = str(v).strip()
    if "T" in s:
        return s.split("T", 1)[0]
    return s[:10] if len(s) >= 10 else s


def _yn(v: Any) -> bool:
    return str(v or "").strip().lower() in {"y", "yes", "true", "1"}


def _str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def parse_commitment_to_annual(text: Any) -> float | None:
    """'$400K/quarter' → 1_600_000; '$55K/month' → 660_000; 'None'/'' → None."""
    s = _str(text)
    if not s or s.lower() == "none":
        return None
    m = re.search(r"\$?\s*([\d.,]+)\s*([kmb])?\s*(?:/|per)?\s*([a-z]+)?", s, re.IGNORECASE)
    if not m:
        return None
    amount = _num(m.group(1))
    if amount is None:
        return None
    mult = _K_PER.get((m.group(2) or "").lower(), 1)
    period = _PERIOD_PER_YEAR.get((m.group(3) or "year").lower(), 1)
    return amount * mult * period


def map_contract(r: dict) -> dict:
    return {
        "id": _str(r.get("Contract_ID")),
        "vendor": _str(r.get("Vendor_Name")),
        "category": _str(r.get("Category")) or "Uncategorised",
        "subcategory": _str(r.get("Subcategory")),
        "region": _str(r.get("Region")),
        "entity": _str(r.get("Region")) or "Group",  # Nexus has no entity; region is the rollup
        "contractValue": _num(r.get("Contract_Value_USD")),
        "acv": _num(r.get("Annual_Value_USD")),
        "start": _iso_date(r.get("Effective_Date")),
        "end": _iso_date(r.get("Expiration_Date")),
        "renewalNoticeDays": _int(r.get("Renewal_Notice_Days")) or 0,
        "autoRenew": _yn(r.get("Auto_Renew")),
        "renewalType": "Auto-renewal" if _yn(r.get("Auto_Renew")) else "Manual",
        "pricingModel": _str(r.get("Pricing_Model")),
        "paymentTerms": _str(r.get("Payment_Terms")),
        "paymentTermDays": _int(re.sub(r"\D", "", str(r.get("Payment_Terms") or "")) or 0) or None,
        "rebateClause": _yn(r.get("Rebate_Clause")),
        "slaPenaltyClause": _yn(r.get("SLA_Penalty_Clause")),
        "volumeCommitmentRaw": _str(r.get("Volume_Commitment")),
        "yearlyCommit": parse_commitment_to_annual(r.get("Volume_Commitment")),
        "owner": _str(r.get("Internal_Owner")),
        "department": _str(r.get("Department")),
        "status": _str(r.get("Contract_Status")) or "Active",
    }


def map_clause(r: dict) -> dict:
    return {
        "contractId": _str(r.get("Contract_ID")),
        "vendor": _str(r.get("Vendor_Name")),
        "clauseType": _str(r.get("Clause_Type")),
        "sectionRef": _str(r.get("Section_Reference")),
        "summary": _str(r.get("Clause_Summary")),
        "keyThreshold": _str(r.get("Key_Threshold")),
        "consequence": _str(r.get("Consequence")),
        "claimWindow": _str(r.get("Claim_Window")),
        "effectiveFrom": _iso_date(r.get("Effective_From")),
    }


def map_invoice(r: dict) -> dict:
    return {
        "id": _str(r.get("Invoice_ID")),
        "vendor": _str(r.get("Vendor_Name")),
        "contractId": _str(r.get("Contract_ID")),
        "po": _str(r.get("PO_Number")),
        "invoiceDate": _iso_date(r.get("Invoice_Date")),
        "dueDate": _iso_date(r.get("Due_Date")),
        "periodStart": _iso_date(r.get("Period_Start")),
        "periodEnd": _iso_date(r.get("Period_End")),
        "lineDescription": _str(r.get("Line_Description")),
        "unit": _str(r.get("Unit")),
        "quantity": _num(r.get("Quantity")),
        "unitPriceBilled": _num(r.get("Unit_Price_Billed")),
        "amount": _num(r.get("Amount_Billed_USD")) or 0.0,
        "paymentStatus": _str(r.get("Payment_Status")),
        "approvedBy": _str(r.get("AP_Approved_By")),
        "notes": _str(r.get("Notes")),
    }


def map_po(r: dict) -> dict:
    return {
        "poNumber": _str(r.get("PO_Number")),
        "vendor": _str(r.get("Vendor_Name")),
        "contractId": _str(r.get("Contract_ID")),
        "poDate": _iso_date(r.get("PO_Date")),
        "department": _str(r.get("Department")),
        "requestor": _str(r.get("Requestor")),
        "approver": _str(r.get("Approver")),
        "lineDescription": _str(r.get("Line_Description")),
        "quantity": _num(r.get("Quantity")),
        "unitPrice": _num(r.get("Unit_Price_USD")),
        "amount": _num(r.get("PO_Amount_USD")) or 0.0,
        "status": _str(r.get("PO_Status")),
    }


def map_inventory(r: dict) -> dict:
    licensed = _num(r.get("Qty_Licensed")) or 0.0
    active = _num(r.get("Qty_Active_90d")) or 0.0
    return {
        "assetId": _str(r.get("Asset_ID")),
        "assetType": _str(r.get("Asset_Type")),
        "vendor": _str(r.get("Vendor_Name")),
        "contractId": _str(r.get("Contract_ID")),
        "productName": _str(r.get("Product_Name")),
        "department": _str(r.get("Department")),
        "location": _str(r.get("Location")),
        "qtyLicensed": licensed,
        "qtyActive90d": active,
        "idleQty": max(0.0, licensed - active),
        "lastActiveDate": _iso_date(r.get("Last_Active_Date")),
        "monthlyCost": _num(r.get("Monthly_Cost_USD")) or 0.0,
        "annualCost": _num(r.get("Annual_Cost_USD")) or 0.0,
        "status": _str(r.get("Asset_Status")),
    }


def map_spend(r: dict) -> dict:
    return {
        "id": _str(r.get("Transaction_ID")),
        "spendDate": _iso_date(r.get("Transaction_Date")),
        "vendor": _str(r.get("Vendor_Name")),
        "contractId": _str(r.get("Contract_ID")),
        "po": _str(r.get("PO_Number")),
        "costCenter": _str(r.get("Cost_Center")),
        "department": _str(r.get("Department")),
        "gl": _str(r.get("GL_Account")),
        "description": _str(r.get("Description")),
        "amount": _num(r.get("Amount_USD")) or 0.0,
        "paymentMethod": _str(r.get("Payment_Method")),
        "invoiceRef": _str(r.get("Invoice_Reference")),
        "fiscalQuarter": _str(r.get("Fiscal_Quarter")),
    }


# Tab name → (mapper, output key in the normalized dataset).
TAB_MAP = {
    "Contracts": (map_contract, "contracts"),
    "Contract Clauses": (map_clause, "clauses"),
    "Invoices": (map_invoice, "invoices"),
    "Purchase Orders": (map_po, "purchaseOrders"),
    "Inventory": (map_inventory, "inventory"),
    "Spend Ledger": (map_spend, "spend"),
}


def map_workbook(tabs: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Apply each tab's mapper; drop rows with no key id. Returns the normalized dataset."""
    dataset: dict[str, list[dict]] = {key: [] for _, key in TAB_MAP.values()}
    for tab, rows in tabs.items():
        entry = TAB_MAP.get(tab)
        if entry is None:
            continue
        mapper, key = entry
        mapped = [mapper(r) for r in rows]
        # Keep rows that carry at least one identifying field.
        dataset[key] = [
            m for m in mapped if any(m.get(k) for k in ("id", "contractId", "poNumber", "assetId"))
        ]
    return dataset
