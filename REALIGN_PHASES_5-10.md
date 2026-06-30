# Realigned Phases 5–10 — Sequential Hardening & Validation

Each phase is reviewed against the realigned vision (Google-Sheets-driven, Agent-Memory,
prototype-matched, NirvanAI), hardened to production quality, tested (6–10 cases), regression-
tested P0→current, and signed off before the next begins.

> Phase mapping (realigned): P0 Foundation · P1 Sheets ingestion · P2 Matching (relationships) ·
> P3 Detection (insights) · P4 Agent Memory · **P5 Core dashboard modules** · P6 NirvanAI ·
> P7 Advanced (Vendors/Indexation/Portfolio) · P8 Line-item & Margin Recovery · P9 Agentic
> automation · P10 Commitment Check & Portfolio Governance.

---

## Phase 5 — Core Dashboard Modules (Power BI-style) ✅

### Implementation summary
The Power-BI-style analytical experience in the `/ci` SPA, reading the Agent Memory snapshot:
- **Dashboard** — 5 headline KPI cards + 3 secondary, "Opportunity by type" bar panel, time-sensitive Alerts.
- **Opportunity Assessment** — EBITDA KPIs + the 4-week decision sprint.
- **Opportunities** — ranked table; expandable rows with rationale, **formula**, recommended action, contract + spend evidence; status workflow (open → in progress → recovered).
- **Spend Explorer** — L1/L2 taxonomy bars + filters (vendor, category, cost-centre, match) + ledger.
- **Contracts** — register with utilisation bars + expandable detail (terms + linked spend).
- **Renewals** — calendar ranked by urgency with uplift exposure.
- **Margin Recovery** — recoverable items grouped by vendor; "Draft challenge letter" → NirvanAI.
- **Data Quality** — match-coverage breakdown + unmatched (maverick) queue + fuzzy-link review.

**Components / files:** `apps/web/app/ci/CostIntelligenceApp.tsx` (added SSR-friendly `initialSnapshot`/`initialTab` props), `lib/ci/compute.ts`, `lib/ci/types.ts`, `app/ci/ci.css`; tests `app/ci/CostIntelligenceApp.test.tsx`; `vitest.config.mts` (alias + automatic JSX).

### Testing summary — 9 UI render tests (server-side, from an injected memory snapshot)
| # | Test | Result |
|---|------|--------|
| 1 | Dashboard KPI widgets + opportunity-by-type + alerts | ✅ |
| 2 | Assessment EBITDA KPIs + 4-week sprint | ✅ |
| 3 | Opportunities ranked table (type/impact/confidence) | ✅ |
| 4 | Spend Explorer L1/L2 taxonomy + ledger (L1 rollup) | ✅ |
| 5 | Contracts register + utilisation | ✅ |
| 6 | Renewals calendar + uplift exposure | ✅ |
| 7 | Margin Recovery grouped by vendor | ✅ |
| 8 | Data Quality match coverage + maverick queue | ✅ |
| 9 | Sidebar renders all 14 modules | ✅ |

`npm test` → **17 passed** (9 Phase-5 UI + 7 NirvanAI/compute + 1 api). tsc 0, ESLint clean, `next build` compiles `/ci`.

### Regression summary — P0–P5
- Backend (P0 foundation, P1 Sheets ingestion, P2 matching/relationships, P3 detection/insights, P4 memory): `ruff` ✅, `mypy` ✅ 182 files, **pytest 155 passed / 4 skipped**.
- Frontend (P5 UI): **17 passed**.

### Issues & fixes
| Issue | Fix |
|-------|-----|
| Mixed npm/pnpm `node_modules` → `jsdom` unresolvable by the root-hoisted vitest; corepack/pnpm unavailable | Pivoted UI tests to **server-side rendering** (`react-dom/server`, node env — no jsdom); set esbuild **automatic JSX** in `vitest.config.mts` |
| SPA fetched only on mount → not headlessly renderable with data | Added optional `initialSnapshot`/`initialTab` props (SSR-friendly; production-safe — live app still fetches) |

### Architecture alignment check
- **HTML prototype** ✅ verbatim CSS + ported views/widgets; sidebar 14 modules.
- **Cost Intelligence architecture** ✅ every view reads `GET /ci/snapshot` (Agent Memory), slices client-side.
- **NirvanAI vision** ✅ global slide-out present on every module (deepened in Phase 6).
- **Agent Memory** ✅ views render purely from the memory snapshot, never the live sheet.
- **Power BI-style dashboard** ✅ KPI cards, bar panels, filterable tables, drill-downs.

### Sign-off gate
✅ dev complete · ✅ phase tests pass · ✅ regression P0–P5 pass · ✅ no critical/high defects · ✅ UI matches prototype (structural + build; visual eyeball recommended) · ✅ workflows operational.

**Minor cleanup (non-blocking):** unused devDeps from the abandoned jsdom path (`@testing-library/*`, `jsdom`, `@vitejs/plugin-react`) can be pruned when the toolchain is on a single package manager.

---

## Phase 6 — NirvanAI Conversational + Document Generation ✅

### Review & realignment
The prototype's NirvanAI is deterministic ask-the-data + 5-document generation (ported to `lib/ci/compute.ts`). The production upgrade: a **Gemini-backed, memory-grounded** conversational endpoint that phrases answers using ONLY facts computed from the Agent Memory snapshot (never inventing figures), with **graceful fallback** to the deterministic answerer when no key/provider. First-party guarantee preserved (benchmark/should-cost questions refused). Reuses the existing model gateway.

### Implementation summary
- **`app/cost_intelligence/nirvana.py`** — `context_facts()` (grounded facts: KPIs + top 8 opportunities + auto-renewals), `deterministic_answer()` (keyword-routed, exact $ from memory; refuses external-data questions), `answer()` (LLM-phrased grounded reply via `model_gateway.complete("fast", …, system=…)`; falls back to deterministic on no-key/error).
- **`POST /api/v1/ci/nirvana/ask`** — reads the latest memory snapshot, returns `{answer, source}` (`llm`|`deterministic`).
- **Frontend** — global slide-out chat + copilot "Ask the data" wired to `/ci/nirvana/ask` (async) with local `nirvanaAnswer` fallback; document generation stays client-side deterministic (`genDoc`, 5 types).

**Files:** `app/cost_intelligence/nirvana.py` (new), `app/api/v1/cost_intelligence_routes.py` (ask route), `apps/web/app/ci/CostIntelligenceApp.tsx` (`askNirvana` helper + chat/copilot wiring), `lib/ci/compute.ts` (fallback + doc gen).

### Testing summary — 12 cases (+1 gated live)
| Area | Tests | Result |
|------|-------|--------|
| Deterministic intents (save-most, recoverable, auto-renew, off-contract) | 4 | ✅ |
| First-party refusal of benchmark questions | 2 | ✅ |
| Grounding context contains real KPIs + top opportunity | 1 | ✅ |
| No-key fallback → deterministic | 1 | ✅ |
| API: ask-before-connect 404, ask-after-connect grounded answer, benchmark refusal | 3 | ✅ |
| Doc generation + answers (compute.ts, Phase-4 carryover) | 7 | ✅ |
| **Live Gemini grounded answer** (gated on key) | 1 | ✅ **validated against the real key** |

Live evidence: *"You can save the most with an unused commit at Accenture LLP, totaling **$1,600,000**."* / *"**$15,166,281** is recoverable right now."* — conversational, figures quoted verbatim from memory (not fabricated).

### Regression summary — P0–P6
- Backend: ruff ✅ · mypy ✅ 183 files · **pytest 166 passed / 5 skipped** (skips = key-gated live LLM tests).
- Frontend: tsc ✅ · ESLint ✅ · **vitest 17 passed**.

### Issues & fixes
| Issue | Fix |
|-------|-----|
| Redis warm cache survived Postgres `TRUNCATE` → "ask before connect" saw a stale snapshot | Test `_truncate()` also clears the `ci:memory:latest` Redis key (test-isolation only; prod always writes both) |
| `nirvana.py` E501 in f-string literals | reflowed / split |
| `record_model_usage` warns in single-workspace (no tenant row for usage accounting) | **non-fatal** — gateway catches it and still returns the answer; usage accounting is a dormant Phase-0 concern. Noted as a minor gap. |

### Architecture alignment check
- **HTML prototype** ✅ chat slide-out + ✦ launcher + ask-the-data chips + document generator unchanged.
- **NirvanAI vision** ✅ now genuinely conversational (LLM-phrased) **and** grounded + first-party + offline-safe.
- **Agent Memory** ✅ every answer is grounded strictly in the memory snapshot.
- **Determinism for money** ✅ the LLM never computes a figure — it quotes memory facts; deterministic fallback guarantees availability.

### Sign-off gate
✅ dev complete · ✅ phase tests pass (incl. live LLM validation) · ✅ regression P0–P6 pass · ✅ no critical/high defects · ✅ UI unchanged from prototype · ✅ AI behaves as expected (grounded, fallback) · ✅ workflows operational.
