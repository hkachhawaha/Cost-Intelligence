"""NirvanaI Assistant — LangGraph StateGraph (§7).

classify_intent (fast) → route → {qa: retrieve → generate → validate_groundedness
(→ regenerate once → reject) | document: select_template → fetch_doc_context →
generate_document | out_of_scope}. All dollar figures come from retrieved/assembled
context (code-computed); the GroundednessValidator is the enforcement gate.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.prompts import (
    DOC_SKELETONS,
    GROUNDED_QA_PROMPT,
    GROUNDED_QA_SYSTEM,
    INTENT_CLASSIFICATION_PROMPT,
    OUT_OF_SCOPE_MESSAGE,
)
from app.core.auth import Principal
from app.core.database import session_for_tenant
from app.core.model_gateway import model_gateway
from app.services.documents import TEMPLATES, document_service
from app.services.groundedness import groundedness_validator
from app.services.rag import RetrievedChunk, rag_service

_RECORD_ID_RE = re.compile(r"record_id=([A-Za-z0-9\-]+)")


class NirvanaState(TypedDict, total=False):
    # inputs
    tenant_id: str
    principal: Principal
    conversation_id: str
    message: str
    module_context: str | None
    history: list[dict]
    run_id: str

    # routing
    intent: Literal["qa", "document", "out_of_scope"]
    doc_template: str | None
    doc_context_ref: dict | None

    # qa path
    retrieved: list[dict]
    answer: str
    citations: list[dict]
    groundedness_ok: bool
    groundedness_reason: str
    regen_attempted: bool

    # document path
    doc_context: dict
    document_body: str
    document_title: str

    # output
    final_text: str
    grounded: bool
    error: str | None


# ── helpers ──────────────────────────────────────────────────────────────────
def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior turns)"
    return "\n".join(f"{t.get('role', 'user')}: {t.get('content', '')}" for t in history)


def _format_doc_context(ctx: dict) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in ctx.items() if v is not None)


def _extract_citations(answer: str, retrieved: list[dict]) -> list[dict]:
    by_id = {c["source_id"]: c for c in retrieved}
    citations: list[dict] = []
    seen: set[str] = set()
    for rid in _RECORD_ID_RE.findall(answer):
        if rid in seen:
            continue
        seen.add(rid)
        chunk = by_id.get(rid)
        if chunk is None:
            continue
        citations.append(
            {
                "type": chunk["source"],
                "record_id": rid,
                "label": chunk.get("label", chunk["source"]),
                "figure": str(chunk["impact"]) if chunk.get("impact") is not None else None,
            }
        )
    return citations


# ── node: classify_intent (gemini-2.5-flash) ───────────────────────────────────
async def classify_intent(s: NirvanaState) -> NirvanaState:
    prompt = INTENT_CLASSIFICATION_PROMPT.format(
        message=s["message"], module_context=s.get("module_context") or "none"
    )
    result = await model_gateway.complete_json(
        "fast",
        prompt,
        tenant_id=s["tenant_id"],
        purpose="intent_classify",
        run_id=s.get("run_id"),
    )
    intent = result.get("intent", "qa")
    if intent not in ("qa", "document", "out_of_scope"):
        intent = "qa"
    return {
        **s,
        "intent": intent,
        "doc_template": result.get("template"),
        "doc_context_ref": result.get("context_ref"),
    }


def route_on_intent(s: NirvanaState) -> str:
    return {
        "qa": "retrieve",
        "document": "select_template",
        "out_of_scope": "respond_out_of_scope",
    }[s["intent"]]


# ── QA path ─────────────────────────────────────────────────────────────────
async def retrieve(s: NirvanaState) -> NirvanaState:
    async with await session_for_tenant(s["tenant_id"]) as session:
        chunks: list[RetrievedChunk] = await rag_service.retrieve(
            s["message"], session=session, principal=s["principal"]
        )
    retrieved = [
        {
            "source": c.source,
            "source_id": c.source_id,
            "text": c.text,
            "impact": c.impact,
            "label": c.label,
        }
        for c in chunks
    ]
    return {**s, "retrieved": retrieved}


def _context_blocks(retrieved: list[dict]) -> str:
    return (
        "\n\n".join(f"[{c['label']}] (record_id={c['source_id']})\n{c['text']}" for c in retrieved)
        or "NO RELEVANT FIRST-PARTY RECORDS FOUND."
    )


async def generate_answer(s: NirvanaState) -> NirvanaState:
    prompt = GROUNDED_QA_PROMPT.format(
        question=s["message"],
        context=_context_blocks(s["retrieved"]),
        history=_format_history(s.get("history", [])),
    )
    res = await model_gateway.complete(
        "complex",
        prompt,
        tenant_id=s["tenant_id"],
        purpose="qa_generate",
        system=GROUNDED_QA_SYSTEM,
        run_id=s.get("run_id"),
    )
    return {**s, "answer": res.text, "citations": _extract_citations(res.text, s["retrieved"])}


async def validate_groundedness(s: NirvanaState) -> NirvanaState:
    outcome = groundedness_validator.validate(s["answer"], s["retrieved"])
    return {**s, "groundedness_ok": outcome.ok, "groundedness_reason": outcome.reason}


def route_after_groundedness(s: NirvanaState) -> str:
    if s["groundedness_ok"]:
        return "finalize_qa"
    if not s.get("regen_attempted"):
        return "regenerate"  # one corrective retry
    return "reject_ungrounded"  # hard fail after retry


async def regenerate(s: NirvanaState) -> NirvanaState:
    prompt = GROUNDED_QA_PROMPT.format(
        question=s["message"],
        context=_context_blocks(s["retrieved"]),
        history=_format_history(s.get("history", [])),
    ) + (
        f"\n\nYOUR PREVIOUS ANSWER WAS REJECTED: {s['groundedness_reason']}. "
        "Re-answer using ONLY dollar figures that appear verbatim in the context above. "
        "If a figure is not in the context, do not state it."
    )
    res = await model_gateway.complete(
        "complex",
        prompt,
        tenant_id=s["tenant_id"],
        purpose="qa_generate_retry",
        system=GROUNDED_QA_SYSTEM,
        run_id=s.get("run_id"),
    )
    return {
        **s,
        "answer": res.text,
        "citations": _extract_citations(res.text, s["retrieved"]),
        "regen_attempted": True,
    }


async def finalize_qa(s: NirvanaState) -> NirvanaState:
    return {**s, "final_text": s["answer"], "grounded": True}


async def reject_ungrounded(s: NirvanaState) -> NirvanaState:
    return {
        **s,
        "grounded": False,
        "citations": [],
        "final_text": (
            "I can't confidently answer that from your data without "
            "stating an unverified figure. Try narrowing the question "
            "(e.g. by vendor or quarter), or open the relevant module."
        ),
    }


# ── document path ─────────────────────────────────────────────────────────────
async def select_template(s: NirvanaState) -> NirvanaState:
    tpl_key = s.get("doc_template") or "supplier_challenge"
    if tpl_key not in TEMPLATES:
        return {**s, "error": f"unknown template {tpl_key}", "intent": "out_of_scope"}
    return {**s, "doc_template": tpl_key}


async def fetch_doc_context(s: NirvanaState) -> NirvanaState:
    tpl: str = s.get("doc_template") or "supplier_challenge"
    ref = s.get("doc_context_ref") or {}
    async with await session_for_tenant(s["tenant_id"]) as session:
        ctx = await document_service.assemble_context(
            tpl, str(ref.get("id")), session=session, principal=s["principal"]
        )
    return {**s, "doc_context": ctx}


async def generate_document(s: NirvanaState) -> NirvanaState:
    tpl: str = s.get("doc_template") or "supplier_challenge"
    skeleton = DOC_SKELETONS[tpl]
    prompt = skeleton.format(context=_format_doc_context(s["doc_context"]))
    res = await model_gateway.complete(
        "complex",
        prompt,
        tenant_id=s["tenant_id"],
        purpose="document_generate",
        system=GROUNDED_QA_SYSTEM,
        run_id=s.get("run_id"),
        max_tokens=2048,
    )
    outcome = groundedness_validator.validate(res.text, [s["doc_context"]])
    title = TEMPLATES[tpl].title_tpl.format(
        vendor=s["doc_context"].get("vendor_name", "Vendor"),
        category=s["doc_context"].get("category", "Category"),
    )
    return {
        **s,
        "document_body": res.text,
        "document_title": title,
        "final_text": res.text,
        "grounded": outcome.ok,
    }


# ── out-of-scope ────────────────────────────────────────────────────────────────
async def respond_out_of_scope(s: NirvanaState) -> NirvanaState:
    return {
        **s,
        "final_text": OUT_OF_SCOPE_MESSAGE,
        "grounded": True,
        "intent": "out_of_scope",
        "citations": [],
    }


# ── graph wiring ────────────────────────────────────────────────────────────────
def build_nirvana_graph():
    g = StateGraph(NirvanaState)
    for node in (
        classify_intent,
        retrieve,
        generate_answer,
        validate_groundedness,
        regenerate,
        finalize_qa,
        reject_ungrounded,
        select_template,
        fetch_doc_context,
        generate_document,
        respond_out_of_scope,
    ):
        g.add_node(node.__name__, node)

    g.set_entry_point("classify_intent")
    g.add_conditional_edges(
        "classify_intent",
        route_on_intent,
        {
            "retrieve": "retrieve",
            "select_template": "select_template",
            "respond_out_of_scope": "respond_out_of_scope",
        },
    )

    # QA path
    g.add_edge("retrieve", "generate_answer")
    g.add_edge("generate_answer", "validate_groundedness")
    g.add_conditional_edges(
        "validate_groundedness",
        route_after_groundedness,
        {
            "finalize_qa": "finalize_qa",
            "regenerate": "regenerate",
            "reject_ungrounded": "reject_ungrounded",
        },
    )
    g.add_edge("regenerate", "validate_groundedness")  # loop back to re-validate
    g.add_edge("finalize_qa", END)
    g.add_edge("reject_ungrounded", END)

    # document path
    g.add_edge("select_template", "fetch_doc_context")
    g.add_edge("fetch_doc_context", "generate_document")
    g.add_edge("generate_document", END)

    # out-of-scope
    g.add_edge("respond_out_of_scope", END)
    return g.compile()


nirvana_graph = build_nirvana_graph()
