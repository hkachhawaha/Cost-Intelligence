"""Anomaly agent (L1, statistical) — §7.3.

Runs the in-code detectors (Z-score / IQR / set-diff / dup-signature), persists flags
as `pending` for human review. No LLM — all math in Python (ML deferred to Phase 9).
"""

from __future__ import annotations

import logging
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.core.database import session_for_tenant
from app.services.anomaly_detection import (
    detect_duplicate_payments,
    detect_new_vendors,
    detect_off_pattern_gl,
    detect_spend_spikes,
)

logger = logging.getLogger("agent.anomaly")


class AnomalyState(TypedDict, total=False):
    tenant_id: str
    run_id: str
    series_by_vendor: dict
    by_gl: dict
    current_vendors: set
    historical_vendors: set
    payment_records: list
    flags: list
    error: str | None


async def run_detectors(s: AnomalyState) -> AnomalyState:
    flags = []
    for _vendor_id, series in (s.get("series_by_vendor") or {}).items():
        flags += detect_spend_spikes(series, z_threshold=settings.anomaly_zscore_threshold)
    flags += detect_off_pattern_gl(s.get("by_gl") or {}, iqr_mult=settings.anomaly_iqr_multiplier)
    flags += detect_new_vendors(
        s.get("current_vendors") or set(), s.get("historical_vendors") or set()
    )
    flags += detect_duplicate_payments(
        s.get("payment_records") or [], window_days=settings.anomaly_dup_window_days
    )
    return {**s, "flags": [f.__dict__ for f in flags]}


async def persist_flags(s: AnomalyState) -> AnomalyState:
    from app.models.advanced import AnomalyFlag

    async with await session_for_tenant(s["tenant_id"]) as session:
        for f in s.get("flags", []):
            session.add(
                AnomalyFlag(
                    tenant_id=UUID(s["tenant_id"]),
                    anomaly_type=f["anomaly_type"],
                    subject_type=f["subject_type"],
                    subject_id=UUID(str(f["subject_id"])),
                    method=f["method"],
                    score=f["score"],
                    detail=f["detail"],
                    status="pending",
                    run_id=UUID(s["run_id"]) if s.get("run_id") else None,
                )
            )
        await session.commit()
    return s


def build_anomaly_graph():
    g = StateGraph(AnomalyState)
    g.add_node("run_detectors", run_detectors)
    g.add_node("persist_flags", persist_flags)
    g.set_entry_point("run_detectors")
    g.add_edge("run_detectors", "persist_flags")
    g.add_edge("persist_flags", END)
    return g.compile()


anomaly_graph = build_anomaly_graph()
