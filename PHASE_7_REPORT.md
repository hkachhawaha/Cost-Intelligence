# Phase 7 — Advanced Modules & Agents: Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 7) and **verified**: backend on Python 3.12 + PostgreSQL 17 + Redis; frontend via TypeScript typecheck + ESLint. Generative agents run on **Google Gemini** through the Phase-6 ModelGateway; all dollar math is Python (§5.6).

## Verification results ✅

| Check | Command | Result |
| ----- | ------- | ------ |
| Backend lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Backend typecheck | `uv run mypy apps/api/app` | ✅ no issues in **131 files** |
| Migration | `uv run alembic upgrade head` (006 → 007) | ✅ 4 tables + 5 spend_records enrichment columns |
| **Backend suite (P0–P7)** | `RUN_DB_TESTS=1 uv run pytest apps/api/tests` | ✅ **92 passed** |
| Phase 7 tests | `pytest test_advanced_unit.py + integration/test_advanced.py` | ✅ **11 passed** |
| Frontend typecheck / lint | `npm run typecheck` / `npm run lint` | ✅ tsc exit 0; ESLint clean |

### Per-phase focused verification (6–10 tests each, as requested)

```
P0  Foundation (RBAC + DB/RLS/audit) ........................... 9 passed
P1  Ingestion (contracts + idempotent UPSERT) .................. 8 passed
P2  Matching (PO/fuzzy/AI-cap + pipeline) ..................... 10 passed
P3  Detection (8 rules + $241K parity) ......................... 8 passed
P4  Memory (build/KPIs/cache/stale/RLS) ........................ 6 passed
P5  Core UI read models ........................................ 8 passed
P6  NirvanaI (groundedness/gateway/RAG-RBAC/audit) ............ 10 passed
P7  Advanced (anomaly/taxonomy/extraction/consolidation/…) .... 11 passed
```

### Phase 7 test breakdown (§14.1/14.2)

```
unit  test_zscore_spike ........................ Z-score flags a spike in a tight series (>3σ)
unit  test_iqr_off_pattern ..................... IQR flags an off-pattern GL amount
unit  test_new_vendor_detect ................... set-diff flags a never-before-seen vendor
unit  test_duplicate_payment_window ............ same vendor+amount within 7d flagged; outside not
unit  test_taxonomy_rules_first ................ keyword rules classify with no model call
unit  test_extraction_schema_and_injection ..... bad date → schema drop; injection markers scanned
unit  test_steward_route_gates_figure_fix ...... merge_vendor (affects_figures) → require_approval
intg  test_consolidation_fragmentation_score ... 4 even vendors → frag 0.75; 2-vendor cat excluded
intg  test_exposure_first_party_formula ........ exposure == ACV×share×move exactly (240k×0.36×0.10=8640)
intg  test_portfolio_rbac ...................... analyst → NotAuthorized; portfolio_admin allowed
intg  test_extraction_human_verification ....... promote (legal) writes edited field to canonical
                                                 + AuditEvent(actor=human); analyst → 403
11 passed
```

## What was built

### Backend

| Area | Files |
| ---- | ----- |
| Models / migration | `models/advanced.py` (ExtractionQueueItem, AnomalyFlag, StewardProposal, IndexRegisterEntry); `migrations/007_advanced.py` (4 RLS tables + 5 `spend_records` enrichment columns); `models/spend.py` (taxonomy/base_amount/fx/confidence) |
| Module services | `services/vendors.py` (rollup + consolidation `fragmentation_score`), `services/indexation.py` (first-party exposure), `services/portfolio.py` (RBAC-gated multi-entity rollup) |
| Agent services | `services/anomaly_detection.py` (Z-score/IQR/new-vendor/dup-payment — all Python), `services/taxonomy.py` (rules-first + LLM fallback), `services/currency.py` (first-party FX) |
| Agents | `agents/extraction.py` (untrusted-input sandbox + schema validation → queue), `agents/enrichment.py` (FX→vendor→taxonomy→persist), `agents/anomaly.py`, `agents/data_steward.py` (figure-affecting gate); `agents/prompts.py` (sandbox/extraction/taxonomy/steward prompts) |
| API | `api/v1/{vendors,indexation,portfolio,extraction,anomalies,data_steward}_routes.py` + `schemas/advanced.py`; registered in `main.py` (16 routes) |
| Config | `core/config.py` — anomaly thresholds, consolidation thresholds, base currency, verify roles |

### Frontend — `apps/web`

| Area | Files |
| ---- | ----- |
| Modules (nav enabled) | `app/(dashboard)/{vendors,indexation,portfolio}/page.tsx`; `components/modules/indexation/exposure-slider.tsx` (interactive first-party slider) |
| Extraction | `app/(dashboard)/extraction/page.tsx` + `components/modules/extraction/verification-queue.tsx` (promote/reject + injection banner) |
| lib | `lib/modules.ts` (vendors/indexation/portfolio → `v1Enabled: true`); `lib/types.ts` (Phase 7 types) |

## DoD highlights met

- **Vendors** surfaces ranked consolidation candidates with a transparent `fragmentation_score = 1 − largest_vendor_share` and rationale — no LLM math (integration-tested: 4 even vendors → 0.75; sub-threshold category excluded).
- **Indexation** models `indexed_exposure = ACV × indexed_share × assumed_move` from **first-party assumptions only** — exact-arithmetic tested (240k × 0.36 × 0.10 = $8,640.00); the slider is the sole input, no external feed.
- **Portfolio** is gated to `portfolio_admin`/`admin` — `NotAuthorized`/403 for other roles (tested).
- **Contract Extraction** is an untrusted-input sandbox: prompt-injection scanned + delimited as data-not-instructions, Pydantic schema-validated (bad fields dropped), and **never auto-commits** — promotion is a human (legal/admin) action that writes verified fields to the canonical Contract + `AuditEvent(extraction.promoted, actor=human)` (tested, including the 403 for non-legal roles).
- **Anomaly** flags spikes (Z-score), off-pattern GL (IQR), new vendors, and duplicate payments — all computed in Python (each detector unit-tested).
- **Data Steward** gates figure-affecting fixes (`affects_figures=true` → `proposed`, human approval) while auto-applying safe ones (logged actor=ai) — gate unit-tested; LLM writes rationale prose only.
- **Determinism for money** holds across the phase: every figure (consolidation, exposure, anomaly stats) is Python; agents only classify/narrate/extract-then-gate.

## Bugs found & fixed during verification

1. **z-score test data** — with only 5 points a single outlier inflates the population std so |z| can't exceed ~√(n−1)≈2; corrected the fixture to a longer tight baseline so a genuine spike scores >3 (the detector itself is correct — it intentionally includes all points).
2. **`.env` inline-comment leak** (surfaced by the per-phase run) — `OTEL_EXPORTER_OTLP_ENDPOINT=  # comment` left the *comment* as the value (dotenv only strips inline comments after a non-empty value), so OTel dialed a bogus channel. Moved the comment to its own line; the endpoint now resolves to blank (disabled).
3. Test-seed FK ordering — added `flush()` between parent/child inserts (vendors→contracts→spend_records/index_register/extraction_queue all carry DB-level FKs).

## Faithful deviations

- **Agents persist via `session_for_tenant`** and the "run" endpoints invoke the LangGraph graphs inline (wrapped in an `AgentRun`) rather than a Celery broker — behavior-identical, runnable/testable offline. The **anomaly run** assembles spend series from the canonical store and runs the pure detectors (no LLM); **extraction/enrichment/steward** LLM nodes lazy-skip without a `GEMINI_API_KEY` (established pattern), so the suite is green offline.
- **Verification queue UI** lives at `/extraction` (reachable by URL); the 12-module sidebar is unchanged (Extraction is an ops surface, not one of the 12 modules). Vendors/Indexation/Portfolio are now `v1Enabled` in the nav.
- The extraction-accuracy + taxonomy evals (§14.3) need a real key + labeled golden set — a keyed-CI follow-up; the deterministic guardrails they protect (schema-drop, injection scan, human-gated promotion) are implemented and tested.

## How to reproduce

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/opt/postgresql@17/bin:$PATH"
cd "Cost Intelligence"
uv run alembic upgrade head                          # → 007
uv run ruff check apps/api && uv run mypy apps/api/app
RUN_DB_TESTS=1 uv run pytest apps/api/tests -q        # 92 passed
cd apps/web && npm run typecheck && npm run lint       # tsc exit 0; ESLint clean
```
