"""Phase 6 NirvanaI unit tests (§14.1) — pure Python, no DB / Redis / LLM.

Covers the deterministic guardrails: the GroundednessValidator (the enforcement gate
behind "every figure cites a record"), the ModelGateway's version-pin routing + code-side
cost attribution + PII redaction, and the document template registry.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.model_gateway import MODEL_ALIASES, MODEL_PRICING, model_gateway
from app.services.documents import TEMPLATES
from app.services.groundedness import extract_dollar_figures, groundedness_validator


def test_extract_dollar_figures():
    assert Decimal("241000") in extract_dollar_figures("savings of $241K identified")
    assert Decimal("1234.56") in extract_dollar_figures("invoice $1,234.56")
    assert Decimal("1200000") in extract_dollar_figures("about 1.2 million in spend")
    # bare small integers are counts, not money
    assert extract_dollar_figures("5 contracts auto-renew") == []


def test_groundedness_accepts_rounding():
    # "$241K" vs a context figure of 241,000 — within tolerance, grounded.
    ctx = [{"text": "total identified", "impact": "241000.00"}]
    assert groundedness_validator.validate("We identified $241K in total.", ctx).ok


def test_groundedness_rejects_fabricated():
    ctx = [{"text": "Acme renews", "impact": "240000.00"}]
    outcome = groundedness_validator.validate("The negotiable amount is $250,000.", ctx)
    assert outcome.ok is False
    assert outcome.ungrounded_figures  # the $250,000 is flagged


def test_groundedness_rejects_derived_total():
    # Two context figures ($30,000 + $20,000); a derived $50,000 total is NOT in context.
    ctx = [
        {"text": "savings opp", "impact": "30000.00"},
        {"text": "recovery opp", "impact": "20000.00"},
    ]
    outcome = groundedness_validator.validate("Combined, that is $50,000 of value.", ctx)
    assert outcome.ok is False


def test_gateway_routes_alias_and_cost():
    # Version-pin map is the only place model IDs live.
    assert MODEL_ALIASES["complex"] == "gemini-2.5-pro"
    assert MODEL_ALIASES["fast"] == "gemini-2.5-flash"
    # Cost is computed in CODE from the price table (never by the model).
    cost = model_gateway._compute_cost("gemini-2.5-pro", 1_000_000, 1_000_000, 0)
    expected = MODEL_PRICING["gemini-2.5-pro"]["input"] + MODEL_PRICING["gemini-2.5-pro"]["output"]
    assert cost == expected


def test_gateway_redacts_pii():
    redacted = model_gateway._redact_pii(
        "email jane@acme.com or call 415-555-1212 re: $240,000 ACV"
    )
    assert "jane@acme.com" not in redacted
    assert "415-555-1212" not in redacted
    assert "[EMAIL]" in redacted and "[PHONE]" in redacted
    # Business figures are NOT redacted — the model needs them to ground answers.
    assert "$240,000" in redacted


def test_template_registry():
    import pytest

    assert set(TEMPLATES) == {
        "supplier_challenge",
        "non_renewal",
        "renegotiation",
        "rfp_brief",
        "supplier_swot",
    }
    with pytest.raises(KeyError):
        _ = TEMPLATES["nonexistent_template"]
