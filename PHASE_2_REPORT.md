# Phase 2 — Spend↔Contract Matching Engine: Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 2) and **verified** against Python 3.12 + PostgreSQL 17 + Redis.

## Verification results ✅

| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Format | `uv run ruff format --check apps/api` | ✅ formatted |
| Typecheck | `uv run mypy apps/api` | ✅ no issues in 74 files |
| Migration | `uv run alembic upgrade head` (002 → 003) | ✅ clean (match_results, unmatched_queue) |
| **Full suite** | `RUN_DB_TESTS=1 uv run pytest apps/api` | ✅ **41 passed** |

### Focused cross-phase run (as requested — 6 tests over phases 0/1/2)

```
test_rls_tenant_isolation .......................... PASSED   (P0 — RLS, load-bearing)
test_agent_run_no_delete_and_terminal_guard ........ PASSED   (P0 — immutable audit)
test_ingestion_collapse_quarantine_drift_audit ..... PASSED   (P1 — vendor collapse + quarantine + drift + records.landed + AgentRun)
test_ingestion_idempotent .......................... PASSED   (P1 — idempotent UPSERT)
test_matching_pipeline_po_and_maverick_idempotent .. PASSED   (P2 — PO-exact 1.0 + maverick queue + idempotency)
test_matching_rls_isolation ........................ PASSED   (P2 — tenant isolation through matching)
6 passed
```

## What was built

| Area | Files |
| ---- | ----- |
| Models | `models/matching.py` — `MatchResult`, `UnmatchedQueue` (CHECK: confidence range, method, unmatched-has-no-contract, **ai_confidence_capped ≤ 0.80**) |
| Migration | `003_matching.py` — both tables, unique-per-spend, partial review index, fail-closed RLS + FORCE |
| Services | `matching.py` (`MatchingService`: PO-exact, weighted fuzzy `0.4/0.3/0.2/0.1`, `amount_similarity`, `date_proximity`, classify bands, human override, full-tenant rematch + maverick-queue sync), `matching_candidates.py`, `matching_lineage.py` (confidence propagation seam, MIN-of-chain) |
| Gateway | `core/model_gateway.py` — minimal LLM chokepoint (Phase 6 expands) |
| Agent | `agents/matching.py` — LangGraph graph (start → match_batch → review? → finalize), AI-inference node with **3-layer 0.80 cap**, `matches.completed` + `match.review_required` events |
| Workers | `workers/matching_tasks.py` — `run_matching`, `rematch_unmatched` |
| API | `api/v1/match_results_routes.py` — list / detail / accept / reassign / rematch / unmatched |
| Evals | `evals/matching/eval_harness.py` + golden set — precision ≥0.90 / recall ≥0.85 / coverage ≥94.9% gate |
| Tests | `tests/test_matching_unit.py`, `tests/integration/test_matching.py` |

## DoD highlights met

- PO matches → confidence `1.000`; fuzzy carries a transparent `score_breakdown`; weights verified to sum to 1.0 (startup assert + unit test).
- **AI-inference confidence provably capped at 0.80** at all three layers: prompt, `min(...,0.80)` in code (unit-tested with a mocked model returning 0.95), and the DB `ai_confidence_capped` CHECK.
- Unmatched spend always lands in `unmatched_queue` (maverick never hidden) — integration-tested.
- Human override flips `matched_by='human'`, confidence authoritative, audited; rematch preserves human rows.
- Idempotent re-run (unique `(tenant, spend)` + UPSERT); tenant isolation holds through matching (non-superuser RLS test).
- Confidence-propagation seam (`confidence_for_spend` / `aggregate_confidence`) ready for Phase 3.

## Faithful deviations

- The agent consolidates the spec's per-tier nodes (`po_match`/`fuzzy_match`/`classify`/`persist`) into one `match_batch` node that calls the deterministic `MatchingService` per spend, keeping LangGraph state lightweight (no ORM objects across nodes/sessions). The conditional review edge + `matches.completed`/`match.review_required` events are preserved.
- Audit uses the existing `core.audit.record_audit_event` (not a parallel `services.audit`).
- Migration 003 RLS uses `NULLIF(...,'')` + `FORCE` (the Phase 0/1 fail-closed correction); no `set_updated_at()` trigger — `updated_at` is handled by the ORM `onupdate`, consistent with prior migrations.
- `MatchingService.run_full_tenant_match` also syncs `unmatched_queue`, so the maverick-queue DoD is satisfied on the deterministic path (not only via the agent).

## Note on the AI path

The AI-inference node calls Anthropic via the model gateway only for still-unmatched spend with candidates. Without an `ANTHROPIC_API_KEY` it degrades gracefully (that spend stays unmatched/maverick — never a hard failure). The 0.80 cap is enforced regardless.
