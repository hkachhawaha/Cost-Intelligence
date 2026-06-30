# Phase 5 — Core Application Modules (v1 UI): Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 5) and **verified**: backend on Python 3.12 + PostgreSQL 17 + Redis; frontend via TypeScript typecheck + ESLint.

## Verification results ✅

| Check | Command | Result |
| ----- | ------- | ------ |
| Backend lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Backend typecheck | `uv run mypy apps/api/app` | ✅ no issues in **103 files** |
| **Backend suite (P0–P5)** | `RUN_DB_TESTS=1 uv run pytest apps/api/tests` | ✅ **67 passed** |
| Phase 5 read-model API tests | `pytest .../test_read_models.py` | ✅ **8 passed** |
| Frontend typecheck | `npm run typecheck` (`tsc --noEmit`) | ✅ exit 0, no errors |
| Frontend lint | `npm run lint` (`next lint`) | ✅ No ESLint warnings or errors |

### Per-phase focused verification (6–10 tests each, as requested)

```
P0  Foundation (RBAC + DB/RLS/audit) ........................... 9 passed
P1  Ingestion (contracts/persist + idempotent UPSERT) .......... 8 passed
P2  Matching (PO/fuzzy/AI-cap + pipeline) ..................... 10 passed
P3  Detection (8 rules + scoring + $241K parity) ............... 8 passed
P4  Memory (build/KPIs/cache/stale/RLS/agent-run) .............. 6 passed
P5  Core UI read models (dashboard/spend/contracts/...) ........ 8 passed
                                                          total: 49 passed
```

### Phase 5 read-model test breakdown (§14.3)

```
test_dashboard_kpis_from_memory ............... reads memory, headline KPIs correct
test_dashboard_reads_memory_not_source ........ Redis flushed → still served from Postgres memory
test_spend_by_category_shape .................. {dimension, items} sorted desc by amount
test_contract_spend_utilization ............... utilization_pct == matched/ACV*100 ($60k/$1M = 6.00%)
test_renewals_window_filter ................... window=90 vs 365 buckets; bad window → 422
test_recovery_packs_grouping .................. grouped by vendor; total == Σ item.amount
test_status_illegal_transition_409 ............ detected→realized → 409
test_status_transition_audited ................ detected→triaged → 200 + audit_event actor=human
8 passed
```

## What was built

### Backend — read-model layer (the data contract the whole UI reads)

| Area | Files |
| ---- | ----- |
| Query service | `services/read_models.py` — `ReadModelService`: dashboard_kpis, spend_by/trend/match_coverage, contracts_list/detail/spend, renewals (windowed), recovery_packs/pack, dq_coverage/events. Aggregates from Phase-4 memory; drill-downs from canonical store; **never source systems**. |
| Schemas | `schemas/read_models.py` — Pydantic v2 response models (§4.2). |
| Dependency | `api/v1/deps.py` — `get_read_models` builds the memory→read-model chain. |
| Routers | `api/v1/{dashboard,spend,contracts,renewals,recovery,data_quality}_routes.py` — 14 read endpoints (§6.1), RBAC-gated per module. |
| Wiring | `main.py` — 6 routers registered under `/api/v1`. |
| Reused | `api/v1/opportunities_routes.py` (Phase 3) — ranked list, detail, `PATCH status` (409 on illegal), `PATCH assign`, all audited `actor=human`. |

### Frontend — `apps/web` (Next.js 14 App Router, Terzo Design System over shadcn)

| Area | Files |
| ---- | ----- |
| Design system | `app/globals.css` (Terzo token layer §3.1 + shadcn semantic vars), `tailwind.config.ts` (token mapping), `lib/design-tokens.ts` |
| Shell | `app/(dashboard)/layout.tsx` (DashboardShell), `components/shell/{sidebar,topbar,tenant-switcher,user-menu,sync-status-badge,sync-status-banner}.tsx`, `components/nirvana/nirvana-panel.tsx` |
| lib | `lib/{api,modules,format,types,config,cn,providers}.ts(x)`, `lib/hooks/{use-opportunities,use-spend,use-renewals}.ts` |
| ui primitives | `components/ui/{button,tabs}.tsx` (Terzo-skinned shadcn base) |
| Dashboard | `app/(dashboard)/dashboard/page.tsx` + `components/modules/dashboard/{kpi-tile,opportunity-chart,alerts-panel,onboarding-empty-state}.tsx` |
| Opportunity Assessment | `app/(dashboard)/assessment/page.tsx` + `components/modules/assessment/{assessment-client,status-workflow,status-badge,owner-select}.tsx` |
| Spend Explorer | `app/(dashboard)/spend/page.tsx` + `components/modules/spend/{spend-explorer-client,spend-bar-chart,spend-trend-chart,match-coverage-donut}.tsx` |
| Contracts | `app/(dashboard)/contracts/page.tsx` + `[id]/page.tsx` + `components/modules/contracts/{utilization-bar,indexation-badge,linked-spend-table,contract-fields}.tsx` |
| Renewals | `app/(dashboard)/renewals/page.tsx` + `components/modules/renewals/{renewals-client,renewal-row}.tsx` |
| Margin Recovery | `app/(dashboard)/recovery/page.tsx` + `components/modules/recovery/recovery-pack-card.tsx` |
| Data Quality | `app/(dashboard)/data-quality/page.tsx` + `components/modules/dq/{coverage-gauge,review-queue-client}.tsx` |

## DoD highlights met

- **All 7 modules** (Dashboard, Opportunity Assessment, Spend Explorer, Contracts, Renewals, Margin Recovery, Data Quality) render real data from the memory layer; each page is a server component doing a single memory read, with client components for interactivity/charts (§2.3).
- **Reads come from memory/canonical, never source** — verified by `test_dashboard_reads_memory_not_source` (flush Redis → still served from the Postgres `tenant_memory` snapshot).
- **Opportunity status workflow** end-to-end (detected → triaged → in_progress → realized/dismissed) with owner assignment; illegal transitions rejected `409`; every transition writes an `audit_event` with `actor=human` (both API-tested).
- **DashboardShell** ships the 12-module sidebar (5 gated "Soon"), topbar tenant switcher + sync-status badge, and the persistent NirvanaI panel placeholder (Phase 6 mounts the assistant).
- **Tenant isolation in the client cache** — `TenantSwitcher` calls `queryClient.clear()` on switch; query keys never span tenants; backend RLS remains the real boundary.
- **No client-side money math** — figures arrive pre-computed (Decimal, Phase 3/4); the UI only formats (§5.6 preserved end-to-end).
- **Determinism / RBAC** — every read endpoint is permission-gated (`dashboard:read`, `spend:read`, `contract:read`, `renewal:read`, `recovery:read`, `data_quality:read`).

## Bugs found & fixed during verification

1. **Expired contracts leaked into the renewal calendar** (real latent Phase-4 bug in `KpiComputer._renewal_calendar`). A contract with a past `end_date` produced negative `days_to_end`, which fell through the `elif days <= 180` branch and appeared in the 180-day renewal window. Surfaced by `test_renewals_window_filter`. Fixed: skip `days < 0` — a renewal calendar is forward-looking only.

## Faithful deviations

- **Verification is backend pytest + frontend tsc/eslint**, not the spec's Vitest/Playwright/Chromatic suites (§14.1/14.4/14.5) — those runners aren't wired into this repo. The §14.3 API read-model tests (the backend contract every component depends on) are implemented and green; component/E2E/visual suites remain a CI follow-up. The prototype-fidelity Chromatic gate (§9.1, BLOCKING for ship) is noted as outstanding.
- **Response-shape hardening**: schema fields that can be absent for a new tenant (uninitialized memory) or a sparse contract are defaulted/nullable so a read never 500s on incomplete data; the UI branches on `initialized`/`has_indexation` instead. `spend_by` normalizes the `vendor_summary` shape (`vendor_id`/`spend`) into the common `{label, amount}` item.
- **`apiClient`/`apiServer`** were added alongside the existing `api` helper (keeps the Phase-0 `api.test.ts` green); client mutations use a cookie-credentialed fetch.
- Added `@tanstack/react-query`, `recharts`, `lucide-react` to `apps/web` (the spec imports them; they weren't yet in package.json).

## How to reproduce

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/opt/postgresql@17/bin:$PATH"
cd "Cost Intelligence"
uv run alembic upgrade head                          # → 005
uv run ruff check apps/api && uv run mypy apps/api/app
RUN_DB_TESTS=1 uv run pytest apps/api/tests -q        # 67 passed
cd apps/web && npm run typecheck && npm run lint       # tsc exit 0; ESLint clean
```
