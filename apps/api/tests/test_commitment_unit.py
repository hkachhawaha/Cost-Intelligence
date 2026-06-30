"""Phase 10 unit tests (§16) — no DB, no network, no LLM.

Commitment Control stress-test math (Python-exact), verdict thresholds, the advisory
invariant, the external-intelligence seam (never subclassed, flag off, methods raise), the
circuit breaker degradation, and tiering policy.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.commitment_control import commitment_control_agent
from app.connectors.external.base import ExternalBenchmarkBase
from app.core.config import settings
from app.core.external_guard import REQUIRES_EXTERNAL_DATA_MSG, external_intelligence_available
from app.schemas.commitment import ProposedDeal


def _deal(**kw) -> ProposedDeal:
    base = dict(acv=Decimal("1200000"), indexed_share=Decimal("0.60"),
                assumed_index_pct=Decimal("0.03"), margin_tolerance=Decimal("800000"))
    base.update(kw)
    return ProposedDeal(**base)


# ── stress-test math (exact Decimal) ──────────────────────────────────────────────
def test_indexed_exposure_formula():
    v = commitment_control_agent.stress_test(_deal())
    assert v.indexed_exposure == Decimal("741600.00")  # 1.2M × 0.60 × 1.03


def test_scenarios_5_10_15_exact():
    v = commitment_control_agent.stress_test(_deal())
    by = {s.move_pct: s.exposure for s in v.scenarios}
    assert by[5] == Decimal("778680.00")  # 741600 × 1.05
    assert by[10] == Decimal("815760.00")  # × 1.10
    assert by[15] == Decimal("852840.00")  # × 1.15


# ── verdict thresholds (positive / edge / negative) ───────────────────────────────
def test_verdict_block_when_10pct_breaches():
    # tolerance 800k: 10% (815,760) and 15% (852,840) breach → block
    v = commitment_control_agent.stress_test(_deal())
    assert v.verdict == "block"


def test_verdict_condition_when_only_15pct_breaches():
    # tolerance 820k: 10% (815,760) ok, 15% (852,840) breaches → condition + index-cap clause
    v = commitment_control_agent.stress_test(_deal(margin_tolerance=Decimal("820000")))
    assert v.verdict == "condition"
    assert any("index-cap" in c or "index ceiling" in c for c in v.conditions)


def test_verdict_approve_when_none_breach():
    v = commitment_control_agent.stress_test(_deal(margin_tolerance=Decimal("900000")))
    assert v.verdict == "approve" and v.conditions == []


def test_advisory_always_true():
    for tol in ("800000", "820000", "900000"):
        v = commitment_control_agent.stress_test(_deal(margin_tolerance=Decimal(tol)))
        assert v.advisory is True


def test_invalid_indexed_share_rejected():
    with pytest.raises(ValidationError):  # rejected at the Pydantic boundary
        ProposedDeal(acv=Decimal("1000"), indexed_share=Decimal("1.5"),
                     assumed_index_pct=Decimal("0.03"), margin_tolerance=Decimal("500"))


# ── external-intelligence seam (first-party guarantee) ─────────────────────────────
def test_external_flag_off_and_message():
    assert external_intelligence_available() is False
    assert settings.external_intelligence_enabled is False
    assert "external market data" in REQUIRES_EXTERNAL_DATA_MSG


def test_external_abc_not_subclassed_and_methods_raise():
    # No concrete subclass exists in the codebase (the seam is never wired in v1–v3).
    assert ExternalBenchmarkBase.__subclasses__() == []
    # And it cannot be instantiated (abstract); a throwaway subclass's methods raise.

    class _Probe(ExternalBenchmarkBase):
        async def market_rate(self, sku, region, currency):
            return await super().market_rate(sku, region, currency)

        async def peer_benchmark(self, category, spend):
            return await super().peer_benchmark(category, spend)

        async def index_forecast(self, index_type, horizon_months):
            return await super().index_forecast(index_type, horizon_months)

    with pytest.raises(NotImplementedError):
        asyncio.run(_Probe().market_rate("sku", "us", "USD"))


# ── circuit breaker (graceful degradation) ─────────────────────────────────────────
def test_circuit_breaker_opens_and_serves_fallback():
    from app.core.quotas import CircuitBreaker

    breaker = CircuitBreaker(failure_threshold=2, reset_seconds=999)
    calls = {"primary": 0, "fallback": 0}

    async def failing():
        calls["primary"] += 1
        raise RuntimeError("provider down")

    async def fallback():
        calls["fallback"] += 1
        return "cached"

    async def run():
        # First two calls fail through to fallback and trip the breaker.
        r1 = await breaker.call("model_provider", failing, fallback)
        r2 = await breaker.call("model_provider", failing, fallback)
        # Now open: the primary is NOT invoked again; fallback served directly.
        r3 = await breaker.call("model_provider", failing, fallback)
        return r1, r2, r3

    assert asyncio.run(run()) == ("cached", "cached", "cached")
    assert calls["primary"] == 2  # breaker stopped the 3rd primary attempt
    assert calls["fallback"] == 3


def test_tiering_policy_hot_warm_cold():
    from datetime import date

    from app.services.tiering import TierManager

    tm = TierManager()
    today = date(2026, 6, 1)
    assert tm.tier_for(date(2026, 5, 1), today) == "hot"  # 1 month old
    assert tm.tier_for(date(2024, 6, 1), today) == "warm"  # 24 months old (<60)
    assert tm.tier_for(date(2019, 1, 1), today) == "cold"  # >60 months old


def test_partition_naming_and_bounds():
    from datetime import date

    from app.services.partitioning import PartitionManager, partition_bounds, partition_name

    assert partition_name(date(2026, 6, 15)) == "spend_records_2026_06"
    assert partition_bounds(date(2026, 6, 15)) == (date(2026, 6, 1), date(2026, 7, 1))
    planned = PartitionManager().planned_partitions(date(2026, 6, 1), ahead_months=2)
    assert planned == ["spend_records_2026_06", "spend_records_2026_07", "spend_records_2026_08"]
