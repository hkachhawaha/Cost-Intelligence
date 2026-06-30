# Phase 10 — v3 Commitment Check & Portfolio Governance: Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 10) and **verified**: backend on Python 3.12 + PostgreSQL 17 + Redis; frontend via tsc + ESLint. This is the **v3 capstone** — the control layer that governs commitments *before* they execute, multi-entity portfolio governance, the first-party seam, and the scalability/degradation framing. All stress-test math is Python Decimal; the verdict is **advisory** and the **human signs**.

## Verification results ✅

| Check | Command | Result |
| ----- | ------- | ------ |
| Backend lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Backend typecheck | `uv run mypy apps/api/app` | ✅ no issues in **173 files** |
| Migration | `alembic upgrade head` (009 → 010) | ✅ 4 tables + NULLIF/FORCE RLS + immutable commitment record |
| **Regression suite (P0–P10)** | `RUN_DB_TESTS=1 uv run pytest apps/api/tests` | ✅ **135 passed, 4 skipped** |
| Phase 10 tests | `pytest test_commitment_unit.py + integration/test_commitment_pipeline.py` | ✅ **20 passed** |
| Frontend | `npm run typecheck` / `npm run lint` / `npm test` | ✅ tsc exit 0; ESLint clean; 1 vitest passed |

> The 4 skips are `test_llm_connectivity.py` (real-Gemini reachability), gated on `GEMINI_API_KEY`. The 10M-row load capstone (`evals/load/test_10m_rows.py`) is a separate gated harness (`RUN_LOAD_TESTS=1`), not part of the offline regression.

### Per-phase regression

```
P0 Foundation ......... 9    P4 Memory ............. 6    P8 Line-item ......... 11
P1 Ingestion .......... 8    P5 Core UI ............ 8    P9 Automation ........ 16
P2 Matching .......... 10    P6 NirvanaI .......... 10    P10 Control layer .... 20
P3 Detection .......... 8    P7 Advanced .......... 11
```

### Phase 10 test cases (positive / negative / edge / error / integration)

```
unit  test_indexed_exposure_formula ................. positive: 1.2M × 0.60 × 1.03 = 741,600.00 exactly
unit  test_scenarios_5_10_15_exact .................. positive: baseline × {1.05,1.10,1.15} exactly
unit  test_verdict_block_when_10pct_breaches ........ 10% breach → block
unit  test_verdict_condition_when_only_15pct_breaches  edge: only 15% breaches → condition + index-cap clause
unit  test_verdict_approve_when_none_breach ......... negative: none breach → approve, no conditions
unit  test_advisory_always_true ..................... invariant: advisory==True in every case
unit  test_invalid_indexed_share_rejected ........... error: indexed_share 1.5 → ValidationError
unit  test_external_flag_off_and_message ............ first-party: flag False; out-of-scope message present
unit  test_external_abc_not_subclassed_and_methods_raise  seam: no subclass; methods raise NotImplementedError
unit  test_circuit_breaker_opens_and_serves_fallback  degradation: trips after N; serves fallback, stops primary
unit  test_tiering_policy_hot_warm_cold ............. edge: hot<12mo, warm<60mo, cold beyond
unit  test_partition_naming_and_bounds .............. pure: spend_records_YYYY_MM + month [start,end) bounds
intg  test_commitment_check_block_and_audit ......... integration: API → block verdict + commitment.checked audit
intg  test_commitment_check_invalid_share_422 ....... error: indexed_share 1.5 → 422 at the boundary
intg  test_commitment_sign_once_then_409 ............ error: sign once (200) → second sign 409 (immutable)
intg  test_commitment_role_gate_403 ................. error: non-allowed role → 403
intg  test_portfolio_vendor_leverage ................ positive: vendor across 2 entities → candidate; single excluded
intg  test_portfolio_rbac_403 ....................... error: non-portfolio_admin → 403
intg  test_health_degradation_reports_state ......... integration: /health/degradation lists degraded subsystem
intg  test_commitment_check_advisory_record_immutable  integration: DELETE on commitment_checks → INSTEAD NOTHING
20 passed
```

## What was built

### Backend — models / migration (NEW/EXT)
```
app/models/commitment.py          # CommitmentCheck, PortfolioRollup, TenantQuota, SpendTierMetadata
app/models/__init__.py            # EXT — registers Phase 10 models
app/core/config.py                # EXT — commitment / external-seam / tiering / quota / NFR settings
migrations/versions/010_control_layer.py   # 4 tables + NULLIF/FORCE RLS + commitment no-delete rule
```

### Backend — agent / services / seam / ops (NEW/EXT)
```
app/agents/commitment_control.py  # L1 advisory stress test (Decimal) + offline-safe LLM rationale
app/schemas/commitment.py         # ProposedDeal, StressScenario, CommitmentVerdict, SignDecision
app/services/commitment.py        # persist immutable check; sign once (AlreadySigned → 409)
app/services/portfolio.py         # EXT — PortfolioGovernanceService: consolidation, vendor leverage, P&L
app/connectors/external/{__init__,base.py}   # ExternalBenchmarkBase ABC — interface only (seam)
app/core/external_guard.py        # external_intelligence_available() + REQUIRES_EXTERNAL_DATA_MSG
app/core/quotas.py                # QuotaService + CircuitBreaker (+ QuotaExceeded/CircuitOpen)
app/core/degradation.py           # DegradationService — graceful-degradation registry
app/services/partitioning.py      # PartitionManager — pure month/partition helpers + ensure/rotate
app/services/tiering.py           # TierManager — hot/warm/cold policy + bookkeeping
app/services/clickhouse_history.py # tenant-predicate-enforcing warm-history access (lazy, degrades)
app/api/v1/commitment_routes.py   # POST/GET/GET{id}/POST sign (role-gated)
app/api/v1/portfolio_routes.py    # EXT — /consolidation, /vendor-leverage, /pnl-impact
app/api/v1/admin_routes.py        # GET/POST /admin/quotas/{tenant_id}
app/api/v1/health_routes.py       # EXT — GET /health/degradation
app/main.py                       # EXT — registers commitment + admin routers
```

### Frontend — `apps/web` (NEW/EXT)
```
app/(dashboard)/commitment/page.tsx
components/modules/commitment/commitment-check-form.tsx   # form → verdict table → sign-off
components/ui/badge.tsx · components/RequiresExternalData.tsx
app/(dashboard)/portfolio/page.tsx (EXT — vendor-leverage section)
lib/modules.ts (EXT — Commitment Check now live) · lib/types.ts (EXT)
```

### Tests / load harness (NEW)
```
tests/test_commitment_unit.py                  # 12 unit (math, verdicts, seam, breaker, tiering, partitions)
tests/integration/test_commitment_pipeline.py  # 8 integration (API, sign 409, RBAC, leverage, degradation, immutability)
evals/load/test_10m_rows.py                    # gated 10M-row capstone (RUN_LOAD_TESTS=1; design per §10.4)
```

## Issues found & fixed during implementation

| # | Issue | Fix |
| - | ----- | --- |
| 1 | `Decimal` used in `models/commitment.py` annotations without import (+ hacky `# type: ignore`) | imported `Decimal`; removed ignores |
| 2 | `portfolio_routes.router` already registered in P7 — re-including would duplicate routes | extended the same router; included it once (P7) |
| 3 | `date` not imported in `portfolio.py` after adding governance methods | added `from datetime import date` |
| 4 | ruff `UP017` (`timezone.utc`) / `B017` (blind `Exception`) | used `datetime.UTC` / `pytest.raises(ValidationError)` |
| 5 | Degradation test hit `/api/v1/health/degradation` (health router mounts at root) | corrected path to `/health/degradation` |
| 6 | Leverage test compared `"2400000"` to API `"2400000.00"` | compare as `Decimal` |

## Design decisions

- **Advisory, never binding.** `CommitmentVerdict.advisory` is always `True`; the engine never signs. Sign-off is a human action recorded immutably (`commitment_checks` no-delete; a second sign-off → 409). The DELETE-does-nothing rule is verified by a live integration test.
- **First-party guarantee held (§3.4).** `ExternalBenchmarkBase` is interface-only, never subclassed (asserted in a test), the flag is `False` and platform-enforced, and no external HTTP egress exists. The index move is an explicit first-party assumption; the UI shows a "requires external data" badge for benchmarking.
- **Determinism for money (§5.6).** Every stress-test figure is Python `Decimal`; the LLM rationale only restates the fixed numbers and is offline-safe — if the model provider is down it degrades to a deterministic summary, so a verdict never blocks on the AI layer.
- **Scalability framed, not faked.** Partition naming/bounds and tiering policy are pure and unit-tested; ClickHouse warm history enforces a mandatory tenant predicate; quotas + an in-process circuit breaker give graceful degradation. The destructive online conversion of `spend_records` to a partitioned table is intentionally left to a dedicated maintenance migration (documented in migration 010), and the 10M-row NFR proof is a gated load harness.
- **Graceful degradation (§15.1).** The read/analysis path depends only on the P4 memory layer + deterministic services. `DegradationService` + `/health/degradation` report which subsystems are degraded; the breaker serves fallbacks instead of erroring.

## Stability

`alembic upgrade head` reaches **010**; `app.main` imports clean; **135 passed / 4 skipped** across P0–P10 with zero regressions; ruff + mypy + tsc + ESLint all green. The app runs correctly. **This completes the phased build (Phases 0–10).**
