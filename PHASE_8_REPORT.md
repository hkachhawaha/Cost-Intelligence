# Phase 8 — v1.5 Line-Item Depth & Recovery: Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 8) and **verified**: backend on Python 3.12 + PostgreSQL 17 + Redis; frontend via tsc + ESLint. All recovery $ math is Python; LLMs only extract/normalize.

## Verification results ✅

| Check | Command | Result |
| ----- | ------- | ------ |
| Backend lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Backend typecheck | `uv run mypy apps/api/app` | ✅ no issues in **143 files** |
| Migration | `alembic upgrade head` (007 → 008) | ✅ rate cards/tiers, recovery_packs, line-item + opportunity coexistence cols, widened CHECKs |
| **Regression suite (P0–P8)** | `RUN_DB_TESTS=1 uv run pytest apps/api/tests` | ✅ **103 passed** |
| Phase 8 tests | `pytest test_line_item_unit.py + integration/test_line_item_pipeline.py` | ✅ **11 passed** |
| Frontend | `npm run typecheck` / `npm run lint` | ✅ tsc exit 0; ESLint clean |

### Per-phase regression (6–10 each)

```
P0 Foundation ......... 9   P3 Detection .......... 8   P6 NirvanaI .......... 10
P1 Ingestion .......... 8   P4 Memory ............. 6   P7 Advanced .......... 11
P2 Matching .......... 10   P5 Core UI ............ 8   P8 Line-item ......... 11
```

### Phase 8 test cases (positive / negative / edge / error / integration)

```
unit  test_above_rate_basic ..................... positive: 0.048 vs 0.042 × 250k → $1,500
unit  test_above_rate_no_overcharge ............. negative: billed == contracted → None
unit  test_above_rate_no_rate_card_advisory ..... edge: no card → requires_rate_card_data, $0, excluded
unit  test_above_rate_null_qty_skipped .......... edge/error: missing qty → skipped, no exception
unit  test_tier_qualifies_cheaper ............... positive: total 600 → tier-2; billed tier-1 → $9,000
unit  test_tier_already_at_best ................. negative: billed == qualified tier → no opp
unit  test_tier_below_floor_no_exception ........ edge: volume below floor → lowest tier, no error
unit  test_coexistence_demotes_header_when_line_covers .. integration: header overspend demoted by line above_rate
unit  test_coexistence_no_demotion_without_overlap ...... negative: unrelated header keeps counting
intg  test_rate_card_verify_gate ................ HITL gate: 403 wrong role, 200 legal, 409 re-verify, audited
intg  test_line_item_pipeline_end_to_end ........ integration: verified cards → detect → recovery pack ($10,500, 3 lines)
11 passed
```

## What was built

### Backend

| Area | Files |
| ---- | ----- |
| Models / migration | `models/rate_card.py` (ContractRateCard, RateCardTier); `models/opportunity.py` (coexistence cols + RecoveryPack + per-line RecoveryItem cols); `models/invoice.py` (line_number/raw_sku/currency/contract_id/rate_card_id); `migrations/008_line_item_depth.py` |
| Rules (pure Python) | `services/rules/above_rate.py`, `services/rules/volume_tier.py` |
| Services | `services/rate_card.py` (verified-only lookup + split tiered), `services/coexistence.py` (header↔line dedup), `services/recovery_pack.py` (per-line evidence), `services/sku_normalization.py`, `services/line_item_detection.py` (orchestration), `services/rate_card_extraction.py` (sandboxed LLM → unverified queue) |
| Schemas / config | `schemas/line_item.py`; `core/config.py` (Phase 8 thresholds + verify roles) |
| API | `api/v1/rate_cards_routes.py` (CRUD, extract, verification-queue, **verify gate**), `api/v1/line_items_routes.py` (ingest, run-line-item, opp line-items, recovery packs); registered in `main.py` (12 routes) |

### Frontend — `apps/web`
`app/(dashboard)/rate-cards/page.tsx` + `components/modules/rate-cards/rate-card-verification-queue.tsx` (the HITL verify surface) + Phase 8 types.

## DoD highlights met

- **Migration 008 applies clean**; rate cards/tiers + recovery packs created, line-item/opportunity columns added, RLS enforced, widened `opp_type_valid`/`opp_status_valid` CHECKs.
- **`detect_above_rate` / `detect_volume_tier` are unit-tested pure functions**; every dollar computed in Python (above_rate $1,500 and volume_tier $9,000 asserted exactly).
- **`requires_rate_card_data`** advisory where no rate card exists — `impact=0`, `counts_in_total=False`, never a false finding (tested).
- **HITL gate**: extracted cards are staged `verified_at=NULL`; only verified cards drive math (`RateCardService` filter); verify is role-gated (legal/category_mgr/admin), 409 on re-verify, audited (tested).
- **Coexistence guard**: a header `overspend` covered by a line-item `above_rate` is demoted (`counts_in_total=False`) and linked, so the same dollars count once (tested); unrelated findings both count.
- **RecoveryPackBuilder** materializes one RecoveryItem per overcharged/under-tiered line; pipeline builds a $10,500 pack with 3 per-line items (tested).
- **Untrusted-input sandbox** for rate-card extraction (prompt-injection wrapper; malformed entries dropped at the Pydantic boundary; LLM never computes a figure).

## Issues identified & fixed

1. **Volume-tier skip condition was inverted** (a real bug in the spec's §5.2 code): `if billed_idx <= qualified_idx: continue` — since a higher tier index is the cheaper rate, recovery exists only when billed at a *lower-index* (more expensive) tier than the aggregate volume qualifies for. The spec's own §14.2 example (billed tier-1, qualified tier-2 → $9,000) is impossible under `<=`. Fixed to `>=` in code, and synced the same fix into the architecture doc.
2. **Opportunity dedup unique-index collision** — Phase 3's `uq_opp_type_contract (tenant,type,contract_id)` would collide for multiple line-item opps. Narrowed both header dedup indexes to `granularity='header'` so line-item opps coexist per invoice/SKU (Phase 3 header behavior preserved).
3. Transient-object defaults — `counts_in_total` (DB default) isn't applied to unpersisted ORM objects; coexistence handles `None` as "still counting" and tests construct with explicit `True`.
4. **Recovery-pack vendor grouping** — the pure rules don't set `vendor_id`; the orchestration now enriches line-item opps with the invoice's `vendor_id` so packs group by vendor (rules stay pure).

## Faithful deviations

- The doc's "Migration 006" is our sequential **008**; `RecoveryPack`/`RecoveryItem` live in `models/opportunity.py` (not a separate `models/recovery`); the P7 extraction LangGraph is left intact and rate-card extraction is exposed as a service + endpoint (no PostgresSaver checkpointer/HITL-interrupt machinery) — same outcome (staged-unverified → human verify), simpler/testable offline.
- Line-item detection is a separate `LineItemDetectionService.run` (additive) rather than mutating Phase-3 `run_all_rules`, preserving header detection and regression safety.
- The rate-card extraction LLM call lazy-skips without `GEMINI_API_KEY` (established pattern); the deterministic rules, gate, coexistence, and recovery pack are fully tested offline. The extraction-accuracy eval (§14.5) remains a keyed-CI follow-up.

## Confirmation

The application is stable end-to-end: migration head at 008, all backend (ruff/mypy/103 tests) and frontend (tsc/eslint) checks green, no runtime/compilation errors. **Ready for Phase 9.**

## How to reproduce

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/opt/postgresql@17/bin:$PATH"
cd "Cost Intelligence"
uv run alembic upgrade head                          # → 008
uv run ruff check apps/api && uv run mypy apps/api/app
RUN_DB_TESTS=1 uv run pytest apps/api/tests -q        # 103 passed
cd apps/web && npm run typecheck && npm run lint
```
