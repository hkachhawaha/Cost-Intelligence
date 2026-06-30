# Cost Intelligence — Realignment Report (v2)

Re-scoped the product to a **single-workspace, Google-Sheets-driven** Cost Intelligence app whose **UI matches the `Designs/Terzo-Cost-Intelligence-App-v2.html` prototype** and whose data is a **connected Google Sheet**, operating from an **Agent Memory** snapshot. Delivered in four validated phases.

---

## 1. Implementation summary

### Phase 1 — Google Sheets data layer (`apps/api/app/cost_intelligence/`)
- **Ingestion** (`sheet_reader.py`): reads a public workbook via its xlsx export (no OAuth); skips each tab's row-1 banner, uses row-2 headers, ignores "Read Me".
- **Schema mapping** (`mappers.py`): per-tab pure mappers → canonical records; type coercion, `Y/N`→bool, `"$400K/quarter"`→annual commitment.
- **Relationship intelligence** (`relationships.py`): resolves spend→contract via **Contract-ID → PO → vendor-exact → vendor-fuzzy → unmatched**; links Contract↔Invoice and Invoice↔Spend.
- **Insights** (`insights.py`): 9 deterministic rules — maverick, overspend, post-expiry, duplicate, auto-renewal, unused-commitment, unclaimed-rebate, off-rate billing, license shelfware — + KPIs. No LLM computes a figure.
- **Agent Memory** (`memory.py`, `models/cost_intelligence.py`, migration `011`): versioned JSONB snapshot in Postgres + warm Redis; app reads memory, Refresh writes a new version.
- **API** (`api/v1/cost_intelligence_routes.py`): `/ci/data-source/{test,connect,refresh}`, `/ci/data-source`, `/ci/snapshot`.

### Phase 2 — UI rebuilt to the prototype (`apps/web/app/ci/`)
- `ci.css` — the prototype's design system ported verbatim (scoped to `.ci-shell`).
- `CostIntelligenceApp.tsx` — faithful SPA: sidebar (14 tabs / 6 groups), all 14 views, NirvanAI global slide-out + ✦ launcher.
- `SettingsView.tsx` — **Settings → Cost Intelligence → Data Source** (URL, name, last sync, status, records; Connect / Test / Refresh / Save).
- `lib/ci/{types,compute}.ts` — snapshot types + ported display/grouping helpers and the deterministic NirvanAI `answer()` / `genDoc()`.
- Root `/` → `/ci`. Every view reads `GET /ci/snapshot` and slices it client-side, exactly like the prototype.

### Phase 3 — Documentation
- **Problem Statement & Blueprint** → new authoritative **§0 Realignment (v2)** (Sheets-primary, agent memory, spreadsheet-driven ingestion, relationship mapping, NirvanAI, prototype-aligned outputs).
- **Full Architecture** → new **Realignment (v2)** section covering the five layers (Data Ingestion, Relationship Intelligence, Agent Memory, NirvanAI, Presentation) + API surface, mapped to real component paths.

### Phase 4 — Tests + this report (below).

---

## 2. Updated architecture summary

```
Google Sheet (public xlsx export, 7 Nexus tabs)
        │  Settings → Connect / Refresh
        ▼
 INGESTION      sheet_reader → mappers            (banner/row-2 aware; type-coerced)
        ▼
 RELATIONSHIPS  resolve spend→contract ladder      Contract↔Invoice · Invoice↔Spend · Contract↔Spend
        ▼
 INSIGHTS       9 deterministic rules + KPIs        (Python math only)
        ▼
 AGENT MEMORY   versioned JSONB snapshot            Postgres (ci_memory_snapshot) + Redis warm
        │  app & NirvanAI read memory, never the live sheet
        ▼
 PRESENTATION   Next.js SPA /ci (14 modules)        + NirvanAI (deterministic answers + doc gen)
```
Single workspace; no login gate (multi-tenant/Auth0/RLS and ERP connectors retained but dormant). Determinism-for-money preserved.

---

## 3. Testing results

| Suite | Result |
| ----- | ------ |
| Backend lint (`ruff`) | ✅ all checks passed |
| Backend typecheck (`mypy`) | ✅ no issues in 182 files |
| **Backend full regression** | ✅ **155 passed, 4 skipped** (skips = key-gated Gemini connectivity) |
| — CI unit tests (`test_cost_intelligence_unit.py`) | ✅ 6 |
| — CI pipeline integration (`test_cost_intelligence_pipeline.py`) | ✅ 3 |
| — **CI E2E scenarios** (`test_ci_e2e_scenarios.py`) | ✅ 11 |
| Frontend `tsc` / `next lint` / `next build` | ✅ clean; `/ci` + all routes compile |
| Frontend tests (`vitest`) | ✅ 8 (incl. 7 NirvanAI/compute) |
| Live sheet validation | ✅ Nexus connect → 944 records, 54 opportunities, $24.96M identified |

### Validation matrix (against the spec's requirements)

| Requirement | Covered by | Status |
| ----------- | ---------- | ------ |
| Spreadsheet connectivity | `test_test_connection_does_not_store`, live connect | ✅ |
| Initial sync | `test_connect_stores_memory_and_status`, `test_scenario_connect_initial_sync` | ✅ |
| Refresh process | `test_refresh_increments_version`, `test_scenario_refresh_rebuilds` | ✅ |
| Contract↔Invoice matching | `test_scenario_contract_invoice_match` | ✅ |
| Invoice↔Spend matching | `test_scenario_invoice_spend_match` | ✅ |
| Contract↔Spend fallback | `test_scenario_contract_spend_fallback` (PO + vendor + maverick) | ✅ |
| Dashboard rendering | `next build` of `/ci`; `test_scenario_dashboard_data_contract` | ✅ (data contract; visual = browser) |
| Insight generation | `test_scenario_insight_generation` (8 rule types) | ✅ |
| NirvanAI responses | `compute.test.ts` (answers + doc gen); `test_scenario_nirvana_data_contract` | ✅ |
| Error handling | `test_scenario_error_handling`, `test_scenario_http_error_returns_400` | ✅ |
| UI matches prototype | verbatim CSS + ported views; `tsc`/`lint`/`build` green | ✅ (visual confirmation in browser) |

---

## 4. Identified gaps / follow-ups

- **Visual UI parity** is verified structurally (verbatim CSS, ported markup, clean build) but final pixel parity needs a **browser eyeball** — open `http://localhost:3000`. No automated visual-regression test yet.
- **NirvanAI is deterministic** (ported from the prototype), not LLM-narrated. The Gemini gateway (Phase 6) is wired and available to upgrade NirvanAI to model-generated narration later; today it answers/drafts from memory deterministically.
- **Public-sheet access only.** Reads assume the sheet is shared "anyone with the link can view." A private-sheet path would reuse the dormant OAuth connector.
- **"Contract compliance" KPI** is surfaced as PO-backed spend % (Nexus resolves by authoritative Contract-ID, so the prototype's PO-only metric reads ~0).
- **Off-rate / rebate parsing** is text-heuristic over clause summaries (rate/threshold regex); robust for the Nexus shape, but unusual clause phrasings could be missed — confidence is set conservatively (0.72–0.80).
- **Single workspace.** The connected sheet is global (one `ci_data_source`); multi-workspace would layer the dormant tenancy back on.
- **Refresh is manual** (by design, per spec). No scheduled auto-refresh.

---

## How to run
1. API: `ENVIRONMENT=local DEV_AUTH_BYPASS=true uv run uvicorn app.main:app --port 8000` (from `apps/api`)
2. Web: `NEXT_PUBLIC_DEV_AUTH=1 NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1 npm run dev` (from `apps/web`)
3. Open **http://localhost:3000** → if empty, **Settings → Connect Spreadsheet** (Nexus URL pre-filled). Full guide in [DEV_RUN.md](DEV_RUN.md).
