"""Relationship intelligence layer. Links the normalized entities and resolves each spend
transaction to a contract by a confidence-ranked ladder:

  1. Contract-ID on the ledger row (Nexus carries it)         → 0.97
  2. PO number → contract (via the PO register)                → 0.95
  3. Vendor exact (normalized name == a contract's vendor)     → 0.85
  4. Vendor fuzzy (token-overlap ≥ threshold)                  → 0.55–0.70
  5. Unmatched (maverick)                                      → 0.00

Also exposes Contract↔Invoice, Invoice↔Spend (via invoice reference, else PO/contract
fallback) so the UI and insights can traverse the graph. Pure functions.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

_STOP = {"inc", "llc", "ltd", "co", "corp", "company", "group", "the", "holdings", "lp", "llp"}


def _norm(s: str | None) -> list[str]:
    s = (s or "").lower().replace("&", " and ")
    s = "".join(c if c.isalnum() or c == " " else " " for c in s)
    return [t for t in s.split() if t and t not in _STOP]


def _token_sim(a: str | None, b: str | None) -> float:
    A, B = _norm(a), _norm(b)
    if not A or not B:
        return 0.0
    used = [False] * len(B)
    matched = 0
    for ta in A:
        for j, tb in enumerate(B):
            if used[j]:
                continue
            if ta == tb or (
                len(ta) >= 4 and len(tb) >= 4 and (ta.startswith(tb) or tb.startswith(ta))
            ):
                used[j] = True
                matched += 1
                break
    return matched / max(len(A), len(B))


def build_relationships(dataset: dict[str, list[dict]]) -> dict[str, Any]:
    """Annotate spend with resolved contract + match metadata; return a relationship summary.
    Mutates spend rows in place (adds resolvedContractId / matchMethod / matchConfidence)."""
    contracts = dataset.get("contracts", [])
    invoices = dataset.get("invoices", [])
    pos = dataset.get("purchaseOrders", [])
    spend = dataset.get("spend", [])

    contract_ids = {c["id"] for c in contracts if c.get("id")}
    po_to_contract = {p["poNumber"]: p.get("contractId") for p in pos if p.get("poNumber")}
    contracts_by_vendor_norm: dict[str, str] = {}
    for c in contracts:
        key = " ".join(_norm(c.get("vendor")))
        if key and key not in contracts_by_vendor_norm:
            contracts_by_vendor_norm[key] = c["id"]
    invoice_ids = {i["id"] for i in invoices if i.get("id")}

    def resolve(s: dict) -> tuple[str | None, str, float]:
        cid = s.get("contractId")
        if cid and cid in contract_ids:
            return cid, "Contract ID", 0.97
        po = s.get("po")
        if po and po_to_contract.get(po) in contract_ids:
            return po_to_contract[po], "PO", 0.95
        vnorm = " ".join(_norm(s.get("vendor")))
        if vnorm and vnorm in contracts_by_vendor_norm:
            return contracts_by_vendor_norm[vnorm], "Vendor (exact)", 0.85
        best, score = None, 0.0
        for c in contracts:
            sim = _token_sim(s.get("vendor"), c.get("vendor"))
            if sim > score:
                best, score = c["id"], sim
        if best and score >= 0.5:
            return best, "Vendor (fuzzy)", 0.70 if score >= 0.99 else 0.55
        return None, "Unmatched", 0.0

    by_method: dict[str, dict] = defaultdict(lambda: {"records": 0, "spend": 0.0})
    contract_to_spend: dict[str, float] = defaultdict(float)
    for s in spend:
        cid, method, conf = resolve(s)
        s["resolvedContractId"] = cid
        s["matchMethod"] = method
        s["matchConfidence"] = conf
        by_method[method]["records"] += 1
        by_method[method]["spend"] += s.get("amount", 0.0)
        if cid:
            contract_to_spend[cid] += s.get("amount", 0.0)

    # Contract ↔ Invoice and Invoice ↔ Spend linkage.
    contract_to_invoices: dict[str, int] = defaultdict(int)
    for inv in invoices:
        if inv.get("contractId") in contract_ids:
            contract_to_invoices[inv["contractId"]] += 1
    invoice_spend_links = sum(
        1 for s in spend if s.get("invoiceRef") and s["invoiceRef"] in invoice_ids
    )

    return {
        "matchByMethod": {k: v for k, v in by_method.items()},
        "poToContract": po_to_contract,
        "contractToSpend": dict(contract_to_spend),
        "contractToInvoiceCount": dict(contract_to_invoices),
        "invoiceSpendLinks": invoice_spend_links,
        "counts": {
            "contracts": len(contracts),
            "invoices": len(invoices),
            "purchaseOrders": len(pos),
            "spend": len(spend),
            "matchedSpendRecords": sum(1 for s in spend if s.get("resolvedContractId")),
            "maverickRecords": sum(1 for s in spend if not s.get("resolvedContractId")),
        },
    }


def contract_index(dataset: dict[str, list[dict]]) -> dict[str, dict]:
    return {c["id"]: c for c in dataset.get("contracts", []) if c.get("id")}


def spend_for_contract(dataset: dict[str, list[dict]], contract_id: str) -> list[dict]:
    return [s for s in dataset.get("spend", []) if s.get("resolvedContractId") == contract_id]
