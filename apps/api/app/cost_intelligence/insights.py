"""Insight generation (deterministic — no LLM computes a figure). Detection rules over the
normalized + related dataset, each emitting an opportunity in the prototype's shape
(type/tag/subject/impact/confidence/rationale/formula/action/evidence/bucket). Plus KPIs.

Rules grounded in the Nexus data: maverick spend, overspend vs ACV, spend after expiry,
duplicate payment, silent auto-renewal, unused commitment, unclaimed rebate (from clauses),
off-rate billing (pricing-schedule clause vs invoice), and license shelfware (inventory).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.core.config import settings

# Recovery (cash-back) vs savings (forward) buckets — mirrors the prototype.
RECOVERY_TYPES = {
    "Overspend vs ACV",
    "Spend after expiry",
    "Duplicate invoice",
    "Unclaimed rebate",
    "Off-rate billing",
}


def _today() -> date:
    if settings.ci_as_of_date:
        return date.fromisoformat(settings.ci_as_of_date)
    return date.today()


def _d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _fmt(n: float) -> str:
    return "$" + f"{round(n):,}"


def _conf_band(c: float) -> str:
    return "high" if c >= 0.85 else "med" if c >= 0.6 else "low"


def generate_opportunities(dataset: dict[str, list[dict]], rel: dict) -> list[dict]:
    s = settings
    today = _today()
    contracts = dataset.get("contracts", [])
    spend = dataset.get("spend", [])
    invoices = dataset.get("invoices", [])
    clauses = dataset.get("clauses", [])
    inventory = dataset.get("inventory", [])
    cidx = {c["id"]: c for c in contracts if c.get("id")}
    spend_by_contract = rel.get("contractToSpend", {})

    def for_contract(cid: str) -> list[dict]:
        return [x for x in spend if x.get("resolvedContractId") == cid]

    opps: list[dict] = []

    # 1) Maverick spend (unmatched).
    mav = [x for x in spend if not x.get("resolvedContractId")]
    mav_exp = sum(x.get("amount", 0.0) for x in mav)
    if mav_exp > 0:
        vendors = {x.get("vendor") for x in mav}
        opps.append(
            {
                "id": "maverick",
                "type": "Maverick spend",
                "tag": "Off-contract",
                "subject": f"{len(mav)} txns · {len(vendors)} vendors",
                "contractId": None,
                "impact": mav_exp * s.ci_recapture_rate,
                "exposure": mav_exp,
                "confidence": 0.78,
                "rationale": f"{_fmt(mav_exp)} of spend across {len(vendors)} vendors has no "
                f"matching contract. Bringing it under contract typically recaptures 5–15%.",
                "formula": f"Exposure = Σ unmatched spend = {_fmt(mav_exp)}\n"
                f"Est. savings = {_fmt(mav_exp)} × {round(s.ci_recapture_rate * 100)}% "
                f"= {_fmt(mav_exp * s.ci_recapture_rate)}",
                "action": f"Consolidate the {len(vendors)} off-contract vendors under negotiated "
                f"agreements; RFP the largest category.",
                "evidence": mav[:50],
            }
        )

    # 2) Overspend vs ACV (recovery).
    for c in contracts:
        acv = c.get("acv") or 0.0
        actual = spend_by_contract.get(c["id"], 0.0)
        over = actual - acv
        if acv > 0 and over > s.ci_overspend_pct * acv:
            opps.append(
                _opp(
                    f"overspend:{c['id']}",
                    "Overspend vs ACV",
                    "Overspend",
                    c,
                    0.85,
                    f"Matched spend {_fmt(actual)} exceeds ACV {_fmt(acv)} by {_fmt(over)}.",
                    f"Overage = Actual − ACV = {_fmt(actual)} − {_fmt(acv)} = {_fmt(over)}",
                    f"Request a rate/line-item audit from {c['vendor']}; reconcile {_fmt(over)} "
                    f"before next payment.",
                    over,
                    for_contract(c["id"])[:50],
                )
            )

    # 3) Spend after expiry (recovery).
    for c in contracts:
        end = _d(c.get("end"))
        if not end:
            continue
        post = [x for x in for_contract(c["id"]) if (_d(x.get("spendDate")) or today) > end]
        amt = sum(x.get("amount", 0.0) for x in post)
        if amt > 0:
            opps.append(
                _opp(
                    f"expiry:{c['id']}",
                    "Spend after expiry",
                    "Post-expiry",
                    c,
                    0.88,
                    f"Contract {c['id']} expired {c['end']}, but {_fmt(amt)} posted after.",
                    f"Post-expiry = Σ spend after End ({c['end']}) = {_fmt(amt)}",
                    f"Stop or re-paper {c['vendor']}; move {_fmt(amt)} onto a current agreement.",
                    amt,
                    post[:50],
                )
            )

    # 4) Duplicate payment (recovery) — same invoice reference, equal amount, >1 occurrence.
    seen: dict[str, list[dict]] = {}
    for x in spend:
        ref = x.get("invoiceRef")
        if ref:
            seen.setdefault(ref, []).append(x)
    for ref, grp in seen.items():
        if len(grp) > 1 and all(abs(g["amount"] - grp[0]["amount"]) < 0.01 for g in grp):
            rec = grp[0]["amount"] * (len(grp) - 1)
            opps.append(
                {
                    "id": f"dup:{ref}",
                    "type": "Duplicate invoice",
                    "tag": "Duplicate",
                    "subject": grp[0].get("vendor"),
                    "contractId": grp[0].get("resolvedContractId"),
                    "impact": rec,
                    "confidence": 0.82,
                    "rationale": f"Invoice reference {ref} ({_fmt(grp[0]['amount'])}) appears "
                    f"{len(grp)} times — likely double payment.",
                    "formula": f"Recoverable = amount × (occurrences − 1) = "
                    f"{_fmt(grp[0]['amount'])} × {len(grp) - 1} = {_fmt(rec)}",
                    "action": f"Issue a debit memo to {grp[0].get('vendor')} for duplicate {ref}; "
                    f"add 3-way-match control.",
                    "evidence": grp[:50],
                    "_vendor": grp[0].get("vendor"),
                }
            )

    # 5) Silent auto-renewal (savings) — auto-renew inside the notice window.
    auto_contracts = set()
    for c in contracts:
        end = _d(c.get("end"))
        if not c.get("autoRenew") or not end or c.get("status") == "Expired":
            continue
        notice = end - timedelta(days=c.get("renewalNoticeDays") or 0)
        days = (notice - today).days
        if days <= s.ci_renewal_lookahead_days:
            acv = c.get("acv") or 0.0
            uplift = acv * s.ci_renewal_uplift_pct
            auto_contracts.add(c["id"])
            past = days < 0
            opps.append(
                _opp(
                    f"autorenew:{c['id']}",
                    "Silent auto-renewal",
                    "Auto-renewal",
                    c,
                    0.90,
                    f"Contract {c['id']} auto-renews. Notice deadline {notice.isoformat()} is "
                    f"{abs(days)} days {'PAST' if past else 'away'}. Assumed "
                    f"{round(s.ci_renewal_uplift_pct * 100)}% uplift on {_fmt(acv)} ACV.",
                    f"Negotiable uplift = ACV × assumed uplift% = {_fmt(acv)} × "
                    f"{round(s.ci_renewal_uplift_pct * 100)}% = {_fmt(uplift)}",
                    f"Send {c['vendor']} renegotiation/non-renewal notice before "
                    f"{notice.isoformat()}.",
                    uplift,
                    for_contract(c["id"])[:20],
                )
            )

    # 6) Unused commitment (savings).
    for c in contracts:
        commit = c.get("yearlyCommit")
        if not commit or commit <= 0:
            continue
        actual = spend_by_contract.get(c["id"], 0.0)
        shortfall = commit - actual
        if shortfall > s.ci_unused_pct * commit:
            opps.append(
                _opp(
                    f"unused:{c['id']}",
                    "Unused commit",
                    "Unused commit",
                    c,
                    0.90,
                    f"Contract {c['id']} commits {_fmt(commit)}/yr but only {_fmt(actual)} matched "
                    f"— {_fmt(shortfall)} unused.",
                    f"Shortfall = Commit − Actual = {_fmt(commit)} − {_fmt(actual)} "
                    f"= {_fmt(shortfall)}",
                    f"Right-size the {c['vendor']} commitment toward {_fmt(actual)} at renewal.",
                    shortfall,
                    for_contract(c["id"])[:20],
                )
            )

    # 7) Unclaimed rebate (recovery) — rebate clause + spend over threshold.
    opps += _rebate_opps(clauses, spend_by_contract, cidx)

    # 8) Off-rate billing (recovery) — invoice unit price above the pricing-schedule rate.
    opps += _off_rate_opps(clauses, invoices, cidx)

    # 9) License shelfware (savings) — licensed but inactive.
    opps += _shelfware_opps(inventory, cidx, s.ci_shelfware_min_idle_pct)

    # Finalize: status, score, bucket, confidence band; rank by impact × confidence.
    for o in opps:
        o["status"] = "open"
        o["conf"] = _conf_band(o["confidence"])
        o["bucket"] = "recovery" if o["type"] in RECOVERY_TYPES else "savings"
        o["score"] = o["impact"] * o["confidence"]
        o["impact"] = round(o["impact"], 2)
    opps.sort(key=lambda o: o["score"], reverse=True)
    return opps


def _opp(oid, otype, tag, c, conf, rationale, formula, action, impact, evidence) -> dict:
    return {
        "id": oid,
        "type": otype,
        "tag": tag,
        "subject": c.get("vendor"),
        "contractId": c.get("id"),
        "impact": impact,
        "confidence": conf,
        "rationale": rationale,
        "formula": formula,
        "action": action,
        "evidence": evidence,
    }


def _rebate_opps(clauses, spend_by_contract, cidx) -> list[dict]:
    out = []
    for cl in clauses:
        if (cl.get("clauseType") or "").lower() != "rebate":
            continue
        rate_m = re.search(r"([\d.]+)\s*%", cl.get("summary") or "")
        thr_m = re.search(r"\$\s*([\d.]+)\s*([kmb])?", cl.get("keyThreshold") or "")
        cid = cl.get("contractId")
        if not (rate_m and thr_m and cid in cidx):
            continue
        rate = float(rate_m.group(1)) / 100
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}.get((thr_m.group(2) or "").lower(), 1)
        threshold = float(thr_m.group(1)) * mult
        actual = spend_by_contract.get(cid, 0.0)
        if actual >= threshold:
            rebate = actual * rate
            c = cidx[cid]
            out.append(
                _opp(
                    f"rebate:{cid}",
                    "Unclaimed rebate",
                    "Rebate",
                    c,
                    0.80,
                    f"Spend {_fmt(actual)} exceeds the {_fmt(threshold)} rebate threshold; a "
                    f"{rate_m.group(1)}% rebate applies but is not reflected in payments.",
                    f"Rebate = spend × rate = {_fmt(actual)} × {rate_m.group(1)}% = {_fmt(rebate)}",
                    f"Claim the {rate_m.group(1)}% rebate from {c['vendor']} "
                    f"({cl.get('claimWindow') or 'per clause'}).",
                    rebate,
                    [],
                )
            )
    return out


def _off_rate_opps(clauses, invoices, cidx) -> list[dict]:
    # Parse the highest $/hr (or $) rate from each contract's pricing-schedule clause.
    sched: dict[str, float] = {}
    for cl in clauses:
        if "pricing" not in (cl.get("clauseType") or "").lower():
            continue
        rates = [
            float(x)
            for x in re.findall(r"\$\s*([\d,]+)", (cl.get("summary") or "").replace(",", ""))
        ]
        if rates and cl.get("contractId"):
            sched[cl["contractId"]] = max(rates)
    out = []
    by_contract: dict[str, list[dict]] = {}
    for inv in invoices:
        cap = sched.get(inv.get("contractId"))
        up = inv.get("unitPriceBilled")
        if cap and up and up > cap * 1.01 and inv.get("quantity"):
            by_contract.setdefault(inv["contractId"], []).append(inv)
    for cid, invs in by_contract.items():
        c = cidx.get(cid)
        if not c:
            continue
        cap = sched[cid]
        over = sum((i["unitPriceBilled"] - cap) * (i.get("quantity") or 0) for i in invs)
        if over <= 0:
            continue
        out.append(
            _opp(
                f"offrate:{cid}",
                "Off-rate billing",
                "Off-rate",
                c,
                0.72,
                f"{len(invs)} invoice line(s) billed above the contracted schedule rate "
                f"({_fmt(cap)}/unit) on contract {cid}.",
                f"Overcharge = Σ (billed − scheduled) × qty = {_fmt(over)}",
                f"Dispute the off-rate lines with {c['vendor']} and request a credit.",
                over,
                invs[:50],
            )
        )
    return out


def _shelfware_opps(inventory, cidx, min_idle_pct) -> list[dict]:
    # Nexus denormalizes the ELA seat totals onto every assignee row, so summing idle across
    # rows would multiply the waste. Group by (contract, product) and take the MAX licensed/
    # active (the ELA-level figures) × the per-seat annual cost — counted once per product.
    by_product: dict[tuple, dict] = {}
    for a in inventory:
        cid = a.get("contractId")
        if not cid:
            continue
        key = (cid, a.get("productName"))
        g = by_product.setdefault(
            key, {"licensed": 0.0, "active": 0.0, "unitAnnual": 0.0, "items": []}
        )
        g["licensed"] = max(g["licensed"], a.get("qtyLicensed", 0.0))
        g["active"] = max(g["active"], a.get("qtyActive90d", 0.0))
        g["unitAnnual"] = max(g["unitAnnual"], a.get("annualCost") or 0.0)
        g["items"].append(a)

    by_contract: dict[str, dict] = {}
    for (cid, _product), g in by_product.items():
        idle = max(0.0, g["licensed"] - g["active"])
        agg = by_contract.setdefault(
            cid, {"licensed": 0.0, "idle": 0.0, "annualCost": 0.0, "items": []}
        )
        agg["licensed"] += g["licensed"]
        agg["idle"] += idle
        agg["annualCost"] += idle * g["unitAnnual"]
        agg["items"].extend(g["items"])

    out = []
    for cid, g in by_contract.items():
        if g["licensed"] <= 0:
            continue
        idle_pct = g["idle"] / g["licensed"]
        if idle_pct >= min_idle_pct and g["annualCost"] > 0:
            c = cidx.get(cid) or {"id": cid, "vendor": g["items"][0].get("vendor")}
            out.append(
                _opp(
                    f"shelfware:{cid}",
                    "License shelfware",
                    "Shelfware",
                    c,
                    0.80,
                    f"{round(g['idle'])} of {round(g['licensed'])} licenses "
                    f"({round(idle_pct * 100)}%) inactive in the last 90 days.",
                    f"Wasted cost = idle seats × annual unit cost = {_fmt(g['annualCost'])}",
                    f"Reclaim/true-down {round(g['idle'])} idle {c.get('vendor')} "
                    f"licenses at renewal.",
                    g["annualCost"],
                    g["items"][:50],
                )
            )
    return out


def compute_kpis(dataset: dict[str, list[dict]], rel: dict, opps: list[dict]) -> dict:
    spend = dataset.get("spend", [])
    total = sum(x.get("amount", 0.0) for x in spend)
    matched = sum(x.get("amount", 0.0) for x in spend if x.get("resolvedContractId"))
    po_spend = sum(x.get("amount", 0.0) for x in spend if x.get("matchMethod") == "PO")
    with_po = sum(1 for x in spend if x.get("po"))
    mav = sum(x.get("amount", 0.0) for x in spend if not x.get("resolvedContractId"))
    identified = sum(o["impact"] for o in opps)
    recovered = sum(o["impact"] for o in opps if o["status"] == "recovered")
    recoverable = sum(o["impact"] for o in opps if o["bucket"] == "recovery")
    savings = sum(o["impact"] for o in opps if o["bucket"] == "savings")

    def pctf(a, b):
        return round(a / b * 100, 1) if b else 0.0

    return {
        "total": round(total, 2),
        "matched": round(matched, 2),
        "po": round(po_spend, 2),
        "maverick": round(mav, 2),
        "identified": round(identified, 2),
        "recovered": round(recovered, 2),
        "recoverable": round(recoverable, 2),
        "savings": round(savings, 2),
        "oppCount": len(opps),
        "spendUnderMgmtPct": pctf(matched, total),
        "compliancePct": pctf(po_spend, total),
        "poCoveragePct": pctf(with_po, len(spend)),
        "recordCounts": rel.get("counts", {}),
    }
