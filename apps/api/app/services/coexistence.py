"""LineItemCoexistenceGuard (§5.4) — reconcile v1 header findings with v1.5 line-item
findings so the same leaked dollars are never double-counted.

Both findings are RETAINED (each is a valid lens). When a line-item `above_rate` opp
explains an invoice a header `overspend` opp also covers, the *header* opp is demoted
(`counts_in_total=False`) and the two are linked via supersedes/superseded_by. The
dashboard/memory total sums only opportunities with `counts_in_total=True`.
"""

from __future__ import annotations

from app.models.opportunity import Opportunity

HEADER_TO_LINE: dict[str, set[str]] = {
    "overspend": {"above_rate"},  # header overspend ⊇ line-item above-rate
}


def reconcile(opps: list[Opportunity]) -> list[Opportunity]:
    by_contract: dict[object, list[Opportunity]] = {}
    for o in opps:
        by_contract.setdefault(o.contract_id, []).append(o)

    for _contract_id, group in by_contract.items():
        headers = [o for o in group if o.granularity == "header"]
        lines = [
            o
            for o in group
            if o.granularity == "line_item" and o.status == "detected" and o.impact > 0
        ]
        for h in headers:
            covering = [line for line in lines if line.type in HEADER_TO_LINE.get(h.type, set())]
            if covering:
                # The precise line-item view counts; demote the header to context-only.
                h.counts_in_total = False
                for line in covering:
                    line.supersedes_id = h.id
                    h.superseded_by_id = line.id
    return opps
