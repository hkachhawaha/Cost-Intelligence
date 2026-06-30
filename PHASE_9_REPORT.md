# Phase 9 — v2 Agentic Automation, ERP Connectors & Continuous Learning: Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 9) and **verified**: backend on Python 3.12 + PostgreSQL 17 + Redis; frontend via tsc + ESLint. The defining invariant — **no irreversible external action without explicit human approval (§5.1)** — is enforced structurally (the agent graph has no send node) *and* in depth (the executor re-checks an approved gate). All money math stays in Python; LLMs never compute figures or approve actions.

## Verification results ✅

| Check | Command | Result |
| ----- | ------- | ------ |
| Backend lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Backend typecheck | `uv run mypy apps/api/app` | ✅ no issues in **159 files** |
| Migration | `alembic upgrade head` (008 → 009) | ✅ 6 tables + NULLIF/FORCE RLS + append-only rules |
| **Regression suite (P0–P9)** | `RUN_DB_TESTS=1 uv run pytest apps/api/tests` | ✅ **115 passed, 4 skipped** |
| Phase 9 tests | `pytest test_workflow_unit.py + integration/test_workflow_pipeline.py` | ✅ **16 passed** |
| Frontend | `npm run typecheck` / `npm run lint` / `npm test` | ✅ tsc exit 0; ESLint clean; 1 vitest passed |

> The 4 skips are `test_llm_connectivity.py` (real-Gemini reachability), gated on `GEMINI_API_KEY` — by design they don't run in the offline regression.

### Per-phase regression (6–10 each)

```
P0 Foundation ......... 9   P3 Detection .......... 8   P6 NirvanaI .......... 10
P1 Ingestion .......... 8   P4 Memory ............. 6   P7 Advanced .......... 11
P2 Matching .......... 10   P5 Core UI ............ 8   P8 Line-item ......... 11
                                                        P9 Automation ........ 16
```

### Phase 9 test cases (positive / negative / edge / error / integration)

```
unit  test_is_actionable_gate ........................ positive + 3 negatives: low conf / wrong type / no deadline
unit  test_coupa_mapper_invoice_and_spend ............ positive: nested supplier/currency, ISO-datetime→date
unit  test_oracle_and_sap_status_normalization ....... edge: PAYMENT_STATUS 'Y'→paid; SAP YYYYMMDD; unknown→open
unit  test_anomaly_zscore_fallback_without_model ..... edge: no fitted model → deterministic P7 Z-score fallback
unit  test_anomaly_train_..._returns_none ............ edge: <50 rows → None (offline-safe, no sklearn needed)
unit  test_dualwrite_tolerates_secondary_failure ..... error: secondary bus raises → primary id still returned
unit  test_fit_weights_never_learns_po_exact ......... invariant: learned weights exclude po_exact (stays 1.0)
unit  test_optimize_thresholds_clamped_to_bounds ..... edge: confirmed impact above max → clamps to config max
intg  test_gated_approve_flow_executes_external_action  integration: opp → awaiting_approval → approve → sent + audited once
intg  test_reject_sends_nothing ...................... negative: reject → cancelled; 0 external actions; decision audited
intg  test_cannot_reapprove_completed_task ........... idempotency: 2nd approve → 404; action fired exactly once
intg  test_record_decision_on_decided_gate_conflicts . error: re-deciding a decided gate → GateAlreadyDecided (409)
intg  test_non_approver_role_forbidden ............... error: role outside approve_roles → 403; 0 external actions
intg  test_executor_refuses_unapproved_gate .......... defense-in-depth: pending gate → UnapprovedActionError
intg  test_illegal_status_transition_conflicts ....... error: open→completed (skips in_progress) → 409
intg  test_recalibration_skips_when_sparse ........... edge: <floor examples → both targets skip (return None)
16 passed
```

## What was built

### Backend — models / migration (NEW/EXT)
```
app/models/automation.py          # Task, ApprovalGate, TaskReminder, ConnectorCredential, LearningLabel, ModelCalibration
app/models/__init__.py            # EXT — registers Phase 9 models
app/core/config.py                # EXT — workflow/learning/anomaly/event-bus settings
migrations/versions/009_agentic_automation.py   # 6 tables + FORCE RLS loop + append-only rules
```

### Backend — services / agent / connectors / API (NEW)
```
app/services/task.py              # TaskService — state machine, approval gates, reminders (audited)
app/services/workflow.py          # WorkflowService — gated loop; approve→execute, reject→nothing
app/services/external_actions.py  # ExternalActionExecutor — the ONLY external-send point; re-verifies gate; idempotent
app/services/feedback_loop.py     # LearningFeedbackService — deterministic recalibration; PO-exact invariant; non-regression guard
app/services/anomaly_ml.py        # IsolationForest (lazy sklearn) + P7 Z-score fallback — offline-safe
app/agents/workflow_automation.py # LangGraph: evaluate_trigger → run_gated_flow → END (NO send node)
app/core/eventbus.py              # EventBus ABC; RedisStreamsBus / KafkaBus (lazy) / DualWriteBus
app/connectors/erp/mappers.py     # CoupaMapper / OracleMapper / SapMapper → Inbound* (pure, tested)
app/connectors/erp/{base,coupa,oracle,sap}.py   # connectors; reshape via mappers, reuse base validate()
app/connectors/registry.py        # EXT — registers coupa/oracle/sap source types
app/api/v1/tasks_routes.py        # list/create/get/patch/status + approve/reject (role-gated)
app/api/v1/learning_routes.py     # GET calibration · POST recalibrate
app/main.py                       # EXT — registers tasks + learning routers
```

### Frontend — `apps/web` (NEW/EXT)
```
app/(dashboard)/tasks/page.tsx
components/modules/tasks/task-approval-queue.tsx   # approve & send / reject (role-gated; inline 403)
lib/modules.ts (EXT — "Workflow Tasks" nav) · lib/types.ts (EXT — WorkflowTask/TasksResponse/TaskDetail)
```

### Tests (NEW)
```
tests/test_workflow_unit.py              # 8 unit (gate, ERP mappers, anomaly fallback, dual-write, learning math)
tests/integration/test_workflow_pipeline.py   # 8 integration (gated approve/reject, executor guard, state machine, sparse learning)
```

## Issues found & fixed during implementation

| # | Issue | Fix |
| - | ----- | --- |
| 1 | `Task.draft_document_id` referenced a non-existent `generated_documents` table | FK → `document_drafts.id` (the real P6 table) |
| 2 | `sklearn` not installed (only `numpy`) | `anomaly_ml` lazy-imports sklearn; falls back to P7 Z-score → always offline-safe |
| 3 | mypy: `httpx.get(headers=...)` got `dict[str, str \| None]` (SAP) | assert `_api_key is not None` after `authenticate()` |
| 4 | mypy: Kafka producer `None`-attr (`union-attr`) | typed `_producer: Any \| None` (optional client, lazy) |
| 5 | registry: `cfg` reused with two config types → mypy redefinition | renamed ERP config local to `erp_cfg` |
| 6 | Integration seed used `bucket="negotiation"` → `opp_bucket_valid` CHECK violation | use a valid bucket (`savings`) |
| 7 | "Double approve → 409" assumption was wrong | after completion there's no pending gate → **404**; reworked into idempotency test (fires once) + a service-level 409 test on `record_decision` |

## Design decisions (HITL gate)

- **Structural + in-depth gate.** The LangGraph agent terminates at `awaiting_approval` (`EXTERNAL_ACTION_NODES` is empty — it *cannot* send). Execution happens only via `POST /tasks/{id}/approve`, and `ExternalActionExecutor` independently re-verifies an `approved` gate before sending. Two independent guarantees, not one.
- **Approvals are role-gated** beyond the permission: only `workflow_approve_roles` (`cfo/legal/category_mgr/admin`) may decide. `approval_gates` is append-only (no delete) — the decision trail is immutable.
- **Learning is deterministic and safe.** Recalibration skips below configured example floors (sparse-safe), clamps thresholds to config bounds, never learns the PO-exact confidence (constant 1.0), and activates a new version only if precision does not regress (prior retained for rollback). `learning_labels` is append-only (no update/delete).
- **Optional deps stay optional.** sklearn (anomaly ML) and aiokafka (event bus) lazy-import and degrade gracefully, so the platform runs — and the full suite passes — with neither installed.

## Stability

`alembic upgrade head` reaches **009**; `app.main` imports clean; **115 passed / 4 skipped** across P0–P9 with zero regressions; ruff + mypy + tsc + ESLint all green. The app runs correctly.
