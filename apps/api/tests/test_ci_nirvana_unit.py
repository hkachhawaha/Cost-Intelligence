"""NirvanAI unit tests (realignment Phase 6) — no DB, no network for the offline cases.

Validates the deterministic, memory-grounded answerer (exact figures from memory), the
first-party refusal of benchmark questions, the grounding-context builder, and the no-key
fallback. A gated test exercises the live Gemini-grounded path when GEMINI_API_KEY is set.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import settings
from app.cost_intelligence import nirvana
from app.cost_intelligence.nirvana import _EXTERNAL_MSG, context_facts, deterministic_answer

SNAP = {
    "kpis": {
        "total": 318000, "identified": 75000, "recoverable": 60000, "savings": 15000,
        "spendUnderMgmtPct": 84.3,
    },
    "spend": [{"id": "T1"}, {"id": "T2"}, {"id": "T3"}],
    "contracts": [{"id": "NXC-1", "vendor": "Acme Cloud"}, {"id": "NXC-2", "vendor": "Globex"}],
    "opportunities": [
        {"id": "overspend:NXC-1", "type": "Overspend vs ACV", "subject": "Acme Cloud",
         "impact": 60000, "bucket": "recovery", "confidence": 0.85},
        {"id": "autorenew:NXC-1", "type": "Silent auto-renewal", "subject": "Acme Cloud",
         "impact": 10000, "bucket": "savings", "confidence": 0.9},
        {"id": "maverick", "type": "Maverick spend", "subject": "1 vendor", "impact": 5000,
         "exposure": 50000, "bucket": "savings", "confidence": 0.78},
    ],
}


def test_deterministic_save_the_most():
    a = deterministic_answer(SNAP, "Where can I save the most?")
    assert "Overspend vs ACV" in a and "$60,000" in a


def test_deterministic_recoverable():
    a = deterministic_answer(SNAP, "What is recoverable right now?")
    assert "$60,000" in a and "recoverable" in a


def test_deterministic_auto_renew():
    a = deterministic_answer(SNAP, "What auto-renews soon?")
    assert "Acme Cloud" in a and "$10,000" in a


def test_deterministic_off_contract():
    a = deterministic_answer(SNAP, "How much spend is off-contract?")
    assert "$50,000" in a  # the maverick exposure


def test_benchmark_question_refused_first_party():
    a = deterministic_answer(SNAP, "Are we paying above market rate?")
    assert a == _EXTERNAL_MSG


def test_context_facts_are_grounded():
    ctx = context_facts(SNAP)
    assert "$318,000" in ctx and "$75,000" in ctx  # total + identified
    assert "Overspend vs ACV" in ctx and "Acme Cloud" in ctx  # top opportunity


def test_answer_without_key_is_deterministic(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    out = asyncio.run(nirvana.answer(SNAP, "Where can I save the most?"))
    assert out["source"] == "deterministic"
    assert out["answer"] == deterministic_answer(SNAP, "Where can I save the most?")


def test_answer_external_question_stays_deterministic(monkeypatch):
    # Even with a key, benchmark questions never reach the LLM.
    monkeypatch.setattr(settings, "gemini_api_key", "fake-key-not-used")
    out = asyncio.run(nirvana.answer(SNAP, "are we paying above market?"))
    assert out == {"answer": _EXTERNAL_MSG, "source": "deterministic"}


@pytest.mark.skipif(not settings.gemini_api_key, reason="no GEMINI_API_KEY configured")
def test_answer_with_gemini_is_grounded():
    """Live Gemini path: an LLM-phrased answer grounded in memory (quotes a real figure)."""
    out = asyncio.run(nirvana.answer(SNAP, "Where can I save the most?"))
    assert out["source"] == "llm"
    assert out["answer"]
    assert "$" in out["answer"]  # grounded in real money figures from memory
