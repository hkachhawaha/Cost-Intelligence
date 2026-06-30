"""Load-test capstone (§13.2, §16.4). Seed 10M spend rows across tenants/periods, then assert
the read-path NFRs hold — served from the P4 memory layer (precomputed KPIs), not live scans.

GATED: this harness is expensive (10M-row seed) and is NOT part of the offline regression
suite (`testpaths = ["apps/api/tests"]`). Run explicitly against a provisioned environment:

    RUN_LOAD_TESTS=1 uv run pytest evals/load/test_10m_rows.py -v

Why the targets hold (design, §10.4): the dashboard/query read path is served from the P4
memory layer (Redis/Postgres precomputed KPIs) — independent of raw row count. Analytical
drilldowns hit ClickHouse columnar warm history (sub-second over 10M+). Postgres stays lean
via partitioning + tiering. Quotas/breakers prevent any tenant from degrading shared latency.
"""

from __future__ import annotations

import os

import pytest

RUN_LOAD_TESTS = os.environ.get("RUN_LOAD_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_LOAD_TESTS,
    reason="RUN_LOAD_TESTS!=1 (10M-row capstone runs only against a provisioned environment)",
)

NFR_DASHBOARD_MS = 5000
NFR_QUERY_MS = 3000
PARTITION_ROW_THRESHOLD = 2_000_000


def test_dashboard_under_5s_at_10m(load_env):
    load_env.seed_spend_rows(10_000_000)
    load_env.rebuild_memory()  # precompute KPIs once
    p95 = load_env.measure(lambda: load_env.client.get("/api/v1/dashboard/kpis"), n=500)
    assert p95 < NFR_DASHBOARD_MS  # < 5s dashboard (memory-served, row-count independent)


def test_query_under_3s_at_10m(load_env):
    p95 = load_env.measure(lambda: load_env.client.get("/api/v1/spend/by-vendor"), n=500)
    assert p95 < NFR_QUERY_MS  # < 3s query (ClickHouse warm drilldown)


def test_partition_count_bounded(load_env):
    for period, count in load_env.partition_row_counts().items():
        assert count < PARTITION_ROW_THRESHOLD, f"partition {period} too large: {count}"


def test_tiering_demote_hot_warm_cold(load_env):
    from datetime import date

    from app.services.tiering import TierManager

    tm = TierManager()
    today = date(2026, 6, 1)
    assert tm.tier_for(date(2026, 5, 1), today) == "hot"
    assert tm.tier_for(date(2024, 6, 1), today) == "warm"
    assert tm.tier_for(date(2018, 1, 1), today) == "cold"


def test_quota_throttles_single_tenant(load_env):
    load_env.set_quota(load_env.noisy_tenant, max_query_qps=5)
    statuses = load_env.hammer(load_env.noisy_tenant, "/api/v1/spend/by-vendor", n=50)
    assert 429 in statuses  # runaway tenant throttled
    # Other tenants unaffected (per-tenant isolation).
    assert all(s == 200 for s in load_env.hammer(load_env.other_tenant, "/api/v1/dashboard/kpis", n=10))


def test_breaker_degrades_not_fails(load_env):
    load_env.kill_model_provider()
    r = load_env.client.get("/api/v1/dashboard/kpis")
    assert r.status_code == 200  # provider down → fallback served, never a 500
