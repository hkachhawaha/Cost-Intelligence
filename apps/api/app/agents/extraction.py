"""Contract Extraction agent (L1, gemini-2.5-pro, SANDBOX) — §5.6, §7.2.

Contract document text is UNTRUSTED: prompt-injection defended (data-not-instructions),
allowlisted (extract-only, no tools), schema-validated. Extracted fields land in the
verification queue — there is intentionally NO "write to canonical" node; promotion is a
human action via the verify endpoint (§6.4).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Literal, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ValidationError

from app.agents.prompts import EXTRACTION_INSTRUCTION, SANDBOX_WRAPPER
from app.core.database import session_for_tenant
from app.core.model_gateway import model_gateway

logger = logging.getLogger("agent.extraction")


class ExtractedContract(BaseModel):
    """Schema the extracted fields MUST validate against before queueing."""

    acv: Decimal | None = None
    tcv: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None
    renewal_type: Literal["auto", "option", "none"] | None = None
    renewal_notice_days: int | None = None
    uplift_pct: Decimal | None = None
    index_type: Literal["CPI", "COLA", "fixed", "custom"] | None = None
    indexed_share: Decimal | None = None


# Cheap heuristic for suspected injection in the document text (flagged, not trusted).
_INJECTION_MARKERS = [
    "ignore previous",
    "ignore the above",
    "disregard",
    "system prompt",
    "you are now",
    "new instructions",
    "assistant:",
    "<|",
    "act as",
]


def scan_injection(document_text: str) -> list[str]:
    low = document_text.lower()
    return [m for m in _INJECTION_MARKERS if m in low]


class ExtractionState(TypedDict, total=False):
    tenant_id: str
    contract_id: str | None
    run_id: str
    source_document: str
    contract_text: str  # UNTRUSTED
    extracted: dict
    extracted_clauses: list
    extracted_rate_card: list
    field_confidence: dict
    injection_flags: list
    needs_verification: bool
    queue_id: str
    error: str | None


async def extract_fields(state: ExtractionState) -> ExtractionState:
    document_text = state["contract_text"]
    injection_flags = scan_injection(document_text)

    prompt = SANDBOX_WRAPPER.format(document=document_text, instruction=EXTRACTION_INSTRUCTION)
    raw = await model_gateway.complete_json(
        "complex",
        prompt,
        tenant_id=state["tenant_id"],
        purpose="contract_extract",
        run_id=state.get("run_id"),
    )

    # Schema validation: anything that doesn't validate is dropped (never canonical).
    try:
        validated = ExtractedContract(
            **{k: v for k, v in raw.items() if k in ExtractedContract.model_fields}
        )
        fields = validated.model_dump(mode="json", exclude_none=True)
        confidence = raw.get("_confidence", {})
    except ValidationError as e:
        fields, confidence = {}, {}
        injection_flags.append(f"schema_validation_failed:{e.error_count()}")

    return {
        **state,
        "extracted": fields,
        "extracted_clauses": raw.get("clauses", []),
        "extracted_rate_card": raw.get("rate_card", []),
        "field_confidence": confidence,
        "injection_flags": injection_flags,
        "needs_verification": True,  # ALWAYS queued for human verification
    }


async def persist_to_queue(state: ExtractionState) -> ExtractionState:
    """Always queue for human verification; NEVER write canonical here."""
    from app.models.advanced import ExtractionQueueItem

    qid = uuid4()
    async with await session_for_tenant(state["tenant_id"]) as session:
        session.add(
            ExtractionQueueItem(
                id=qid,
                tenant_id=UUID(state["tenant_id"]),
                contract_id=UUID(state["contract_id"]) if state.get("contract_id") else None,
                source_document=state.get("source_document", ""),
                extracted_fields=state.get("extracted", {}),
                extracted_clauses=state.get("extracted_clauses", []),
                extracted_rate_card=state.get("extracted_rate_card", []),
                field_confidence=state.get("field_confidence", {}),
                injection_flags=state.get("injection_flags", []),
                status="needs_verification",
                run_id=UUID(state["run_id"]) if state.get("run_id") else None,
            )
        )
        await session.commit()
    return {**state, "queue_id": str(qid)}


def build_extraction_graph():
    g = StateGraph(ExtractionState)
    g.add_node("extract_fields", extract_fields)
    g.add_node("persist_to_queue", persist_to_queue)
    g.set_entry_point("extract_fields")
    g.add_edge("extract_fields", "persist_to_queue")
    g.add_edge("persist_to_queue", END)
    return g.compile()


extraction_graph = build_extraction_graph()
