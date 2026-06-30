"""NirvanAI — conversational cost-intelligence over the Agent Memory snapshot.

`answer()` is **grounded**: it computes deterministic FACTS from memory (exact $ figures), then
— if Gemini is configured — asks the model to phrase a conversational reply using ONLY those
facts, forbidden from inventing or altering any number. With no key / on any error it returns
the deterministic answer verbatim. Money is never computed by the LLM (determinism guarantee).
First-party only: benchmark/should-cost questions are refused.
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger("ci.nirvana")

_EXTERNAL_MSG = (
    "That needs external market data (benchmarks / should-cost), which is outside the scope of "
    "Terzo Cost Intelligence — it works from your first-party spend and contracts only."
)
_SYSTEM = (
    "You are NirvanAI, a first-party cost-intelligence assistant. Answer the user's question "
    "in 1–3 sentences using ONLY the FACTS provided (computed from the customer's own spend and "
    "contracts). Never invent, estimate, or alter any dollar figure or vendor name — quote them "
    "exactly as given. If the FACTS do not answer the question, say so plainly. Do not reference "
    "external market data or benchmarks."
)


def _fmt(n: float) -> str:
    return "$" + f"{round(n or 0):,}"


def context_facts(snapshot: dict) -> str:
    """Compact, grounded facts from memory — the only ground truth the LLM may use."""
    k = snapshot.get("kpis", {})
    opps = snapshot.get("opportunities", [])
    contracts = snapshot.get("contracts", [])
    lines = [
        f"Total spend: {_fmt(k.get('total', 0))} across {len(snapshot.get('spend', []))} records.",
        f"Spend under management: {k.get('spendUnderMgmtPct', 0)}%.",
        f"Identified opportunity: {_fmt(k.get('identified', 0))} "
        f"(recoverable {_fmt(k.get('recoverable', 0))}, "
        f"savings {_fmt(k.get('savings', 0))}).",
        f"Contracts: {len(contracts)}; opportunities: {len(opps)}.",
        "Top opportunities:",
    ]
    for o in opps[:8]:
        lines.append(
            f"  - {o.get('type')} · {o.get('subject') or '—'} · {_fmt(o.get('impact', 0))} "
            f"({o.get('bucket')}, confidence {o.get('confidence')})"
        )
    auto = [o for o in opps if o.get("type") == "Silent auto-renewal"]
    if auto:
        lines.append(
            "Auto-renewals in window: "
            + ", ".join(f"{o.get('subject')} ({_fmt(o.get('impact', 0))})" for o in auto[:5])
        )
    return "\n".join(lines)


def deterministic_answer(snapshot: dict, raw: str) -> str:
    """Keyword-routed answer straight from memory (fallback + grounding seed). Exact figures."""
    q = (raw or "").lower()
    k = snapshot.get("kpis", {})
    opps = snapshot.get("opportunities", [])

    if any(
        w in q
        for w in (
            "benchmark",
            "market rate",
            "should cost",
            "should-cost",
            "vs market",
            "above market",
        )
    ):
        return _EXTERNAL_MSG
    if "save the most" in q or "biggest" in q or "top" in q:
        t = opps[:3]
        return (
            "Your highest-impact opportunities: "
            + "; ".join(
                f"{o.get('type')} — {o.get('subject') or ''} ({_fmt(o.get('impact', 0))})"
                for o in t
            )
            + f". Combined {_fmt(sum(o.get('impact', 0) for o in t))}."
        )
    if "auto-renew" in q or "auto renew" in q:
        t = [o for o in opps if o.get("type") == "Silent auto-renewal"]
        return (
            f"{len(t)} contract(s) auto-renew within the notice window: "
            + ", ".join(f"{o.get('subject')} ({_fmt(o.get('impact', 0))})" for o in t)
            + "."
            if t
            else "No auto-renewals in the current window."
        )
    if "recover" in q:
        return (
            f"{_fmt(k.get('recoverable', 0))} is recoverable now — duplicates, "
            "overspend, post-expiry and unclaimed rebates."
        )
    if "off-contract" in q or "maverick" in q:
        m = next((o for o in opps if o.get("id") == "maverick"), None)
        return (
            f"{_fmt(m.get('exposure', 0))} of spend is off-contract; about "
            f"{_fmt(m.get('impact', 0))} is recapturable."
            if m
            else "No off-contract (maverick) spend detected."
        )
    if "expir" in q:
        return (
            f"Identified opportunity totals {_fmt(k.get('identified', 0))}; "
            "see Renewals for contracts nearing term."
        )
    if "save" in q or "saving" in q:
        return (
            f"Future savings total {_fmt(k.get('savings', 0))} (renewals, commitments, shelfware)."
        )
    return (
        f"From your data: {_fmt(k.get('total', 0))} total spend, "
        f"{_fmt(k.get('identified', 0))} identified "
        f"({_fmt(k.get('recoverable', 0))} recoverable, {_fmt(k.get('savings', 0))} savings) "
        f"across {len(opps)} opportunities. Ask about auto-renewals, what's recoverable, "
        "or where to save the most."
    )


async def answer(snapshot: dict, question: str) -> dict:
    """Grounded conversational answer. LLM phrases the deterministic facts; falls back to them."""
    det = deterministic_answer(snapshot, question)
    # External-data refusal and the no-key path stay deterministic.
    if det == _EXTERNAL_MSG or not settings.gemini_api_key:
        return {"answer": det, "source": "deterministic"}
    try:
        from app.core.model_gateway import model_gateway

        ctx = context_facts(snapshot)
        prompt = (
            f"FACTS (the only ground truth — never alter a number or name):\n{ctx}\n\n"
            f'A deterministic draft answer is: "{det}"\n\n'
            f"User question: {question}\n\n"
            "Reply conversationally using only the FACTS above."
        )
        res = await model_gateway.complete(
            "fast",
            prompt,
            tenant_id=settings.dev_tenant_id,
            purpose="ci_nirvana",
            max_tokens=2000,
            system=_SYSTEM,
        )
        text = (res.text or "").strip()
        return {"answer": text or det, "source": "llm" if text else "deterministic"}
    except Exception as exc:  # noqa: BLE001 — never block on the AI layer
        logger.warning("ci.nirvana.degraded err=%s", exc)
        return {"answer": det, "source": "deterministic"}
