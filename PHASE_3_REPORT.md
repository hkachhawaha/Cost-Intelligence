# Phase 3 — Detection Rule Engine: Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 3) and **verified** against Python 3.12 + PostgreSQL 17 + Redis.

## Verification results ✅

| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Typecheck | `uv run mypy apps/api` | ✅ no issues in 95 files |
| Migration | `uv run alembic upgrade head` (003 → 004) | ✅ clean (opportunities, recovery_items) |
| **Full suite** | `RUN_DB_TESTS=1 uv run pytest apps/api` | ✅ **53 passed** |
| **$241K eval parity** | detection eval harness | ✅ **$241,050** (savings $162,400 + recovery $78,650) — within 0.02% of $241K |

### Eval breakdown (synthetic dataset)

```
maverick           2,400.00   (savings)   auto_renewal      70,000.00   (savings)
unused_commitment 20,000.00   (savings)   uplift_creep      70,000.00   (savings)
overspend         30,400.00   (recovery)  duplicate_invoice 48,250.00   (recovery)
grand_total      241,050.00   (passes ±3% gate)
```

### Focused cross-phase run (P0 → P3)

```
P0  test_rls_tenant_isolation ............................... PASSED
P1  test_ingestion_idempotent ............................... PASSED
P2  test_matching_pipeline_po_and_maverick_idempotent ....... PASSED
P3  test_detection_creates_and_propagates_confidence ........ PASSED
P3  test_status_machine_enforces_transitions ................ PASSED
P3  test_eval_harness_reproduces_241k ...................... PASSED
6 passed
```

## What was built

| Area | Files |
| ---- | ----- |
| Models | `models/opportunity.py` — `Opportunity` (partial unique dedup indexes, CHECKs incl. `impact ≥ 0`, dismiss-reason guard), `RecoveryItem` |
| Migration | `004_detection.py` — both tables, fail-closed RLS + FORCE, dedup indexes, rank index |
| Rules (8 pure fns) | `services/rules/{maverick,unused_commitment,overspend,auto_renewal,uplift_creep,post_expiry,duplicate_invoice,missing_invoice}.py` + `_types.RuleFinding` |
| Services | `detection.py` (`run_all_rules` + `_load_reconciled` + upsert dedup + auto-dismiss), `scoring.py` (impact×conf → time-sensitivity → effort), `opportunity_status.py` (§8.3 state machine) |
| Agents | `agents/detection.py` (L2, no LLM, emits `opportunities.detected`), `agents/recommendation.py` (L1, `claude-sonnet-4-6` cited rationale + groundedness guard) |
| Workers | `workers/detection_tasks.py` |
| API | `api/v1/opportunities_routes.py` — ranked list (with code-computed bucket totals), detail, status PATCH, assign, `POST /detection/run` |
| Evals | `evals/detection/eval_harness.py` + `golden/synthetic_dataset.json` |
| Tests | `tests/test_detection_rules.py`, `tests/integration/test_detection.py` |

## DoD highlights met

- All **8 v1 rules** are pure functions matching the Appendix A formulas exactly; every rule unit-tested; each emits a transparent `evidence` dict (formula + inputs + record ids).
- `run_all_rules` **upserts by (type, contract_id)** → re-running produces no duplicates (integration-tested); vanished opportunities auto-dismiss with `no_longer_detected` (status never regresses below a human-advanced state).
- **Synthetic dataset reproduces ~$241K** (within ±3%), correctly split savings/recovery, with a per-type breakdown so a compensating-error bug can't pass.
- **Confidence propagation** — opportunity confidence is the min-of-chain match confidence (the unused-commitment opp inherits the 0.80 match conf; integration-tested).
- **Determinism for money** — every dollar figure is computed in Python; the Recommendation LLM receives the figure as a fixed input and a groundedness guard rejects any rationale containing a different dollar figure (the opp keeps no rationale rather than a fabricated one).
- **Lifecycle state machine** enforces §8.3; illegal transitions raise (→ `409`); owner required before `in_progress`; reason required to dismiss; every transition audited.
- `opportunities.detected` fires with code-computed `totals` + `by_type`.

## Faithful deviations

- The detection agent consolidates the spec's per-node stubs into `start_run → run_and_persist → finalize`, calling `DetectionService.run_all_rules` (which does the load/dispatch/score/upsert). Functionally identical; LangGraph state stays lightweight.
- Audit uses the existing `core.audit.record_audit_event` (not a parallel `services.audit`).
- `_load_reconciled` (left as `...` in the doc) is fully implemented as set-based loads over contracts/match_results/spend/invoices, deriving `matched_by_contract`, `confidence_by_contract` (min-of-chain), `unmatched_spend`, and `invoice_pos_by_contract`.
- Migration 004 RLS uses `NULLIF(...,'')` + `FORCE` (the Phase 0/1/2 fail-closed correction); no `set_updated_at()` trigger — `updated_at` is handled by the ORM `onupdate`.
- The eval harness runs the rules over an in-memory fixture (via `DetectionService.run_rules_over`) rather than seeding the DB — fast, deterministic, DB-free; `_load_reconciled` is separately covered by the integration test.

## Spec bugs found & fixed

1. `RuleFinding` lacked the `vendor_id` field that `duplicate_invoice` passed → added it.
2. `duplicate_invoice` had a stray `... if hasattr(RuleFinding, "__dataclass_fields__") else None` clause → removed; appends findings normally.
