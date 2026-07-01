# Cost Intelligence — Product Summary

**Prepared for:** Staff PM onboarding
**Platform:** Terzo Cost Intelligence
**Date:** June 2026
**Status:** Built (Phases 0–10 complete), deployed to Vercel

---

## What Is This?

Cost Intelligence is an AI-powered spend-to-contract reconciliation platform built for enterprise finance and procurement teams. It answers a core business problem: **companies sign contracts defining what they should pay, but actual spend drifts from those terms — and nobody catches it until money is already lost.**

The platform ingests three data sets (Contracts, Invoices, Spend Transactions), links them together, runs a deterministic rule engine to surface leakage and savings opportunities, and presents them through a 14-module dashboard with an AI assistant (NirvanaI) that can answer natural-language questions and draft supplier letters.

**On a representative dataset ($1.69M spend across 10 contracts), the working prototype identified ~$241K of opportunity at 94.9% match coverage.**

---

## The Core Value Proposition

> Every dollar an enterprise spends is continuously reconciled against what it agreed to pay, and every new commitment is validated before it is signed.

**What makes it defensible:**
- Built entirely on **first-party data** — no external benchmarks, no market comparisons
- Every figure is traceable back to the specific invoice line or contract clause that produced it
- AI is used for language and judgment; **all financial math runs in deterministic Python code**

---

## Who Is It For?

| Persona | Primary Goal | Key Modules |
|---|---|---|
| CFO / Finance Leader | Protect margin; trust the numbers | Portfolio, Dashboard, Opportunities |
| CPO / Procurement Leader | Prioritize savings; manage renewals | Renewals, Opportunity Assessment, Vendors |
| Category / Sourcing Manager | Run sourcing events | Spend Explorer, NirvanaI (RFP drafts) |
| AP / Finance Analyst | Recover cash; clean data | Margin Recovery, Data Quality |
| Legal / Contract Owner | Manage terms & risk | Contracts, Indexation |

---

## How Data Flows In

The platform uses a **"ingest-once, operate-from-memory"** model:

1. User connects a Google Sheet (the primary data source for v1) in **Settings → Data Source**
2. The system reads all tabs (Contracts, Contract Clauses, Invoices, Purchase Orders, Inventory, Spend Ledger)
3. It builds relationships: Contract ↔ Invoice ↔ Spend
4. It runs detection rules and generates opportunities
5. All results are stored in a versioned memory snapshot (Postgres + Redis)
6. The app and NirvanaI serve from this snapshot — **never re-querying the sheet live**
7. A manual **Refresh** re-reads and rebuilds everything

ERP connectors (SAP, Oracle, Coupa) exist in the codebase but are dormant; Google Sheets is the active path.

---

## The 14 Product Modules

### Overview Group
| Module | What It Does | Key Value |
|---|---|---|
| **Home / Dashboard** | KPI tiles, "we found money" hero, top action cards, spend-by-category donut, alerts panel | At-a-glance health and savings headline |
| **Opportunities** | Ranked list of all detected savings/recovery items with formula, evidence, and recommended action | Prioritized "act first" plan |

### Analyze Group
| Module | What It Does | Key Value |
|---|---|---|
| **Analyze Hub** | AI-generated insights, spend trend, supplier performance, utilization, variance | Strategic overview |
| **Spend Explorer** | Spend broken down by vendor, category, cost center; trend charts; match coverage | Full spend visibility |
| **Contracts** | Contract register with terms, utilization bars, indexation, linked spend; drills to contract detail page | The contractual "should" |
| **Vendors** | Supplier rollup with concentration analysis and consolidation candidates | Leverage and rationalization |
| **Indexation & Exposure** | Index/COLA-linked contracts with exposure slider showing cost risk under different index moves | Forward cost-risk visibility |

### Act Group
| Module | What It Does | Key Value |
|---|---|---|
| **Act Hub** | Actions grouped by recommended-action category | Operational triage |
| **Margin Recovery** | Per-vendor recovery packs with evidence; "Draft with NirvanaI" to generate challenge letters | Recoverable cash |
| **Renewals** | Calendar of upcoming renewals sorted by urgency; auto-renewal flags; uplift exposure quantified | Act before deadlines |
| **Commitments** | Pre-signature stress test (±5/10/15%); approve / condition / block verdict | Govern new spend before it's signed |
| **Commitment Check** | Form to run a commitment stress test against a specific deal | Line-level commitment control |

### Intelligence Group
| Module | What It Does | Key Value |
|---|---|---|
| **NirvanaI** | Conversational Q&A from first-party data; drafts renegotiation emails, non-renewal notices, RFP briefs, supplier SWOTs | Ask-the-data + document generation |
| **Portfolio** | Multi-entity rollup with group-level spend, SUM, and opportunity concentration | Group-level visibility |

### System Group
| Module | What It Does | Key Value |
|---|---|---|
| **Data Quality** | Match-coverage donut, unmatched spend queue, fuzzy-match review | Trust and transparency |
| **Settings / Data Source** | Connect Google Sheet, configure assumptions, trigger Refresh | Source configuration |

---

## What Leakage Types Are Detected

The detection engine runs 8 rules. Every finding carries an impact $, confidence score, formula, rationale, and recommended action:

| Opportunity Type | Bucket | Description |
|---|---|---|
| **Maverick / Off-Contract Spend** | Savings | Spend with no matching contract |
| **Unused Commitment** | Savings | Contracted volume not consumed |
| **Overspend vs ACV** | Recovery | Actual spend exceeds annual contract value |
| **Silent Auto-Renewal** | Savings | Contract auto-renewing inside notice window |
| **Uplift Creep** | Savings | Renewal price increasing above prior term |
| **Spend After Expiry** | Recovery | Payments made after contract end date |
| **Duplicate Invoice** | Recovery | Same invoice paid more than once |
| **Missing Invoice** | Control | Spend or PO with no corresponding invoice |

---

## The AI Layer (NirvanaI + Agents)

NirvanaI is the conversational face of the platform. It:
- Answers questions grounded in the Agent Memory snapshot ("what auto-renews this quarter?", "where is the biggest exposure?")
- Drafts documents: renegotiation emails, non-renewal notices, supplier challenge letters, RFP briefs, supplier SWOTs
- Is available as a global slide-out on every module and as a dedicated module

**Behind NirvanaI, there are 12 specialized agents:**

| Agent | Role |
|---|---|
| Ingestion | Lands, validates, dedupes source data |
| Enrichment | Normalizes vendors, currency, GL; classifies to taxonomy |
| Matching | Links spend ↔ contract (PO-first, then fuzzy); scores confidence |
| Contract Extraction | Extracts terms, clauses, rate cards from documents |
| Detection | Runs the 8-rule leakage/savings engine |
| Anomaly | Flags statistical outliers, spikes, new vendors, duplicate patterns |
| Recommendation | Ranks opportunities; advises next action |
| Document/Action | Drafts letters, RFPs, SWOTs, memos |
| Workflow Automation | Creates tasks, routes approvals, sends notifications (human-gated) |
| Commitment Control | Stress-tests a proposed deal; returns approve/condition/block verdict |
| NirvanaI (Assistant) | Conversational Q&A and drafting |
| Data Steward | Monitors data quality; proposes fixes for normalization gaps |

**Key guardrail:** No agent takes an irreversible external action (sending a supplier letter, cancelling a contract) without explicit human approval. All financial math is Python code — never an LLM.

---

## Technical Architecture (Brief)

| Layer | Technology |
|---|---|
| Backend API | Python / FastAPI |
| Frontend | Next.js / React / Tailwind CSS |
| Database | PostgreSQL (with pgvector for embeddings, Redis for KPI cache) |
| Agent Framework | LangGraph |
| LLM / Embeddings | Google Gemini (`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-embedding-001`) |
| Auth | Auth0 (multi-tenant infra built; dormant for single-workspace v1) |
| Deployment | Vercel (frontend: `cost-intelligence-web.vercel.app`) + backend separately |
| ERP Connectors | SAP, Oracle, Coupa (built, not active) |

The platform is built for enterprise scale: designed for 10M+ spend transactions, 1M+ invoices, 500K+ contracts per tenant. Match latency target: seconds from landing to matched.

---

## Build Phases Summary

The platform was built across 11 phases:

| Phase | What Was Built |
|---|---|
| 0 | Monorepo scaffold, multi-tenant Postgres, Auth0, audit log, CI/CD |
| 1 | Google Sheets connector, 95-field canonical data model, ingestion agent |
| 2 | Spend ↔ contract matching engine (PO-exact + fuzzy + AI inference) |
| 3 | 8-rule detection engine, opportunity entity, lifecycle state machine |
| 4 | Agent Memory layer (ingest-once model), KPI compute, sync pipeline |
| 5 | 7 core UI modules (Dashboard, Assessment, Spend, Contracts, Renewals, Recovery, Data Quality) |
| 6 | NirvanaI conversational assistant (RAG, groundedness, document drafting) |
| 7 | Vendors, Indexation, Portfolio modules + Enrichment, Extraction, Anomaly, Data Steward agents |
| 8 | Line-item depth: above-rate and volume-tier recovery rules, rate card extraction |
| 9 | Agentic automation, ERP connectors (SAP/Oracle/Coupa), event bus, continuous learning loop |
| 10 | Commitment Check (pre-signature control), portfolio governance, scalability framing |

---

## Roadmap (What's Next)

| Horizon | Theme | Scope |
|---|---|---|
| **Now (v1)** | First-party detection | Current state — matching, 8 detection rules, dashboard, recovery, renewals, NirvanaI |
| **Next (v1.5)** | Line-item & recovery depth | Above-rate & volume-tier rules active; richer recovery packs; deeper indexation |
| **Next (v2)** | Agentic automation | Full agent layer in production; workflow automation; anomaly ML models; continuous learning |
| **Later (v3)** | Control & portfolio | Commitment Control at scale; multi-entity portfolio governance; optional external intelligence |

---

## Key Product Decisions & Constraints

1. **First-party data only** — no external benchmarks in v1. Questions like "are we paying above market?" are explicitly labeled "requires external data." This is a deliberate, defensible wedge.
2. **Determinism for money** — all $ figures computed in Python code, not by an LLM. Non-negotiable for trust.
3. **Human-in-the-loop for external actions** — agents draft; humans send. No autonomous supplier communications.
4. **Single workspace for v1** — multi-tenant Auth0/RLS infrastructure is built but dormant. The running product is one workspace, Google Sheets as source.
5. **Confidence on everything** — every spend-to-contract match and every opportunity carries a confidence score derived from match quality. Low-confidence items route to human review, never to auto-action.

---

# API Reference

All APIs are under `/api/v1/` and require authentication. Permissions are role-scoped per tenant.

---

## Data Ingestion & Source Management

### `GET/POST/DELETE /data-sources`
**What:** Manage connected data sources (Google Sheets, ERP connectors).
**Why:** This is the entry point for all data. A procurement team connects their Google Sheet here; the system registers it as a data source and stores credentials or the public URL.

### `POST /data-sources/{id}/refresh`
**What:** Trigger a re-pull of data from a connected source.
**Why:** Since the platform operates from a memory snapshot, this is how users get updated data into the system without triggering a full re-sync.

### `GET /data-sources/{id}/batches`
**What:** List ingestion batches for a data source (showing what landed and when).
**Why:** Gives ops/admins visibility into ingestion history and lets them debug data issues.

### `GET /staging/quarantine` · `POST /staging/quarantine/{id}/resolve`
**What:** View and resolve records that failed validation during ingestion.
**Why:** The Ingestion agent quarantines records that violate the data contract (wrong types, missing required fields) rather than silently corrupting downstream data. Humans resolve these.

### `GET /google-sheets/oauth/start` · `GET /google-sheets/oauth/callback`
**What:** OAuth flow for Google Sheets connection (admin-only).
**Why:** Allows connecting private Google Sheets via OAuth rather than a public export URL. Not the primary path for v1 (public URL is), but available for more controlled setups.

---

## Sync (Memory Management)

### `POST /sync/initial`
**What:** Run the full initial sync — reads the connected source, builds all relationships, runs detection, writes the Agent Memory snapshot.
**Why:** This is the core pipeline trigger. Running it for the first time populates the entire platform. Nothing works until an initial sync runs.

### `POST /sync/refresh`
**What:** Re-run the sync against the current data source to update the memory snapshot.
**Why:** The platform operates from a cached snapshot. When the underlying Google Sheet changes, a Refresh re-reads it, rebuilds relationships, and regenerates all opportunities and KPIs.

### `GET /sync/status`
**What:** Returns the current sync status (running, completed, failed) and metadata (last sync time, record counts).
**Why:** The frontend shows a sync status badge; this powers it. Also useful for debugging stuck syncs.

---

## Dashboard & KPIs

### `GET /dashboard/kpis`
**What:** Returns the main KPI tiles: spend under management (SUM), contract compliance %, PO coverage %, total identified opportunity $, total recoverable $, total savings $.
**Why:** These are the headline numbers on the Home module. They power the "we found money" hero section and the executive overview.

---

## Opportunities

### `GET /opportunities`
**What:** Paginated, filterable list of all detected opportunities. Filters: type (maverick, overspend, auto_renewal, etc.), bucket (savings/recovery), status (open, in_progress, realized, dismissed), owner, min/max impact.
**Why:** This is the core output of the detection engine. The Opportunity Assessment module is built on this. Everything prioritized here maps to a dollar-quantified, evidenced finding.

### `GET /opportunities/{id}`
**What:** Full detail for a single opportunity including impact $, confidence, rationale, formula, evidence (linked spend records), recommended action, and lifecycle history.
**Why:** The "drill-down" on any opportunity card in the UI. Also used when generating recovery letters or NirvanaI answers about a specific finding.

### `PATCH /opportunities/{id}/status`
**What:** Move an opportunity through its lifecycle: open → in_progress → realized → dismissed.
**Why:** Tracks realization of savings/recovery. The key metric for proving value: identified → in-progress → recovered.

### `PATCH /opportunities/{id}/owner`
**What:** Assign an opportunity to a user.
**Why:** Enables workflow — a procurement leader assigns recoveries to AP analysts, renewals to category managers.

### `POST /opportunities/run-detection`
**What:** Manually trigger the detection rule engine.
**Why:** Used after a sync or data change to recompute all opportunities. Also triggered automatically after each sync.

---

## Spend

### `GET /spend/by-vendor`
**What:** Spend aggregated and ranked by vendor with match coverage per vendor.
**Why:** The primary view in Spend Explorer's vendor tab. Also powers vendor consolidation analysis.

### `GET /spend/by-category`
**What:** Spend aggregated by taxonomy category (L1/L2).
**Why:** Category-level spend visibility — the category manager's primary lens.

### `GET /spend/by-cost-center`
**What:** Spend aggregated by cost center.
**Why:** Finance and FP&A view — allocating spend to business units.

### `GET /spend/trend`
**What:** Month-over-month spend trend data.
**Why:** Powers the spend trend chart. Helps procurement leaders see if spend is growing, concentrating, or shifting.

### `GET /spend/match-coverage`
**What:** Match coverage summary — how much spend is matched to a contract vs. unmatched (maverick).
**Why:** The key data quality signal. Powers the "Spend Under Management" KPI and the match coverage donut chart in Data Quality.

---

## Contracts

### `GET /contracts`
**What:** Paginated contract list with key fields: vendor, ACV/TCV, start/end dates, renewal type, utilization %, match coverage.
**Why:** The contract register — the backbone of the platform. Every opportunity traces back to a contract.

### `GET /contracts/{id}`
**What:** Full contract detail: all 95+ fields including terms, clauses, indexation, rate cards, and AI-extracted data.
**Why:** The contract drill-down page. Legal teams use this; also used by NirvanaI when answering questions about a specific contract.

### `GET /contracts/{id}/spend`
**What:** All spend records linked to a specific contract, with match confidence and amount.
**Why:** The "linked spend" tab on the contract detail page. Shows procurement teams exactly what was purchased under each contract.

---

## Vendors

### `GET /vendors`
**What:** Canonical vendor list with spend total, contract count, match coverage, and consolidation opportunity score.
**Why:** The Vendors module. Procurement leaders use this to see concentration risk and identify consolidation opportunities.

### `GET /vendors/consolidation-candidates`
**What:** Vendors with fragmented spend across multiple contracts or entities where consolidation would improve leverage.
**Why:** A specific procurement action — identifying where the company could negotiate better by combining volumes.

---

## Renewals

### `GET /renewals`
**What:** Upcoming contract renewals filtered by a time window, sorted by urgency. Includes: notice deadline, auto-renewal flag, uplift %, and quantified uplift exposure in $.
**Why:** The Renewals module. This is the time-sensitive view — showing what will auto-renew if no action is taken, and what it will cost.

---

## Margin Recovery

### `GET /recovery/packs`
**What:** Recovery packs grouped by vendor — each pack contains the recoverable items (duplicates, post-expiry, overspend), total recoverable $, and evidence.
**Why:** The Margin Recovery module. AP analysts use this to build a supplier challenge. Each pack is designed to be sent as a structured claim to the vendor.

### `GET /recovery/{id}`
**What:** Detail on a specific recovery pack with full line-level evidence.
**Why:** Used when reviewing or drafting a challenge letter for a specific vendor.

---

## Indexation & Exposure

### `GET /indexation/register`
**What:** List of all contracts with index/COLA clauses — showing index type, uplift %, and indexed share of contract value.
**Why:** The Indexation module. Legal and finance teams use this to understand which contracts have cost escalation clauses.

### `GET /indexation/exposure`
**What:** Calculates total index exposure across all indexed contracts under a configurable assumed index move (e.g., CPI +3%).
**Why:** Powers the exposure slider — lets finance model "if inflation hits X%, what is our total exposure?"

### `PUT /indexation/register/{contract_id}`
**What:** Manually set or override indexation register fields for a contract.
**Why:** Allows corrections where the AI-extracted indexation data is wrong or incomplete.

---

## Data Quality

### `GET /data-quality/coverage`
**What:** Match coverage breakdown: % matched by method (PO, fuzzy, AI-inferred), % unmatched, confidence distribution.
**Why:** The Data Quality module's main view. Shows how trustworthy the downstream numbers are — the higher the match coverage, the higher the confidence in every KPI.

### `GET /data-quality/events`
**What:** Data quality events and issues: schema violations, quarantined records, low-confidence matches, normalization gaps.
**Why:** Operational monitoring for data teams. Shows what's broken and what needs human review.

---

## Match Results

### `GET /match-results`
**What:** Paginated list of all spend-to-contract match results with method, confidence, and any discrepancies.
**Why:** The unmatched queue and fuzzy-match review queue in the Data Quality module.

### `GET /match-results/unmatched`
**What:** All spend records with no acceptable match (the maverick queue).
**Why:** Unmatched spend is a direct input to the maverick opportunity calculation. This also shows what the team needs to investigate.

### `PATCH /match-results/{id}/reassign`
**What:** Human override to reassign a match result to a different contract.
**Why:** When the automated match is wrong, a data steward corrects it here. This also feeds the continuous learning loop.

### `PATCH /match-results/{id}/accept`
**What:** Human accepts a low-confidence automated match.
**Why:** Low-confidence matches go to review rather than auto-action. Acceptance confirms them and promotes their confidence.

### `POST /match-results/rematch`
**What:** Re-run the matching engine on a set of spend records.
**Why:** Used after corrections or after a new contract is added — to catch matches that weren't possible before.

---

## NirvanaI (Conversational AI)

### `POST /nirvana/chat`
**What:** Send a message to NirvanaI; returns a streaming SSE response (grounded answer or out-of-scope message).
**Why:** The core conversational interface. Powers the chat panel available on every module. All answers are grounded in Agent Memory — no fabricated figures.

### `POST /nirvana/generate-doc`
**What:** Generate a document draft (renegotiation email, non-renewal notice, supplier challenge letter, RFP brief, supplier SWOT).
**Why:** The "Draft with NirvanaI" action throughout the UI. Creates an editable document draft — the human reviews and sends it.

### `PATCH /nirvana/drafts/{id}`
**What:** Update or approve a generated document draft.
**Why:** Human review gate — drafts are never sent automatically. This is how a procurement manager edits and approves a generated letter before it goes to a supplier.

### `GET /nirvana/drafts`
**What:** List all generated document drafts with status (draft, approved, sent).
**Why:** The document library — procurement teams can review, edit, or reuse previously generated documents.

### `GET /nirvana/history`
**What:** Conversation history for NirvanaI.
**Why:** Context continuity — lets users resume past conversations and see what questions were asked and answered.

---

## Commitment Check (Pre-Signature Control)

### `POST /commitment`
**What:** Run a commitment stress test for a proposed deal. Input: deal value, index-linked share, assumed index move, term. Output: exposure under ±5/10/15% scenarios + approve/condition/block verdict.
**Why:** The Commitment Check module. Before a procurement manager signs a new contract, they run it through this to see worst-case indexed exposure and get an advisory verdict against the company's margin tolerance.

### `GET /commitment`
**What:** List all past commitment checks with outcomes.
**Why:** Audit trail of pre-signature decisions — useful for governance and for reviewing what was assessed before contracts were signed.

### `GET /commitment/{id}`
**What:** Detail on a single commitment check with full stress-test math.
**Why:** Drill-down into the analysis behind a specific verdict.

### `POST /commitment/{id}/sign`
**What:** Mark a commitment check as "signed" — records that the human accepted and proceeded.
**Why:** Completes the pre-signature control loop. Immutable once signed (can't be undone).

---

## Portfolio

### `GET /portfolio`
**What:** Multi-entity spend rollup: spend by legal entity/business unit with SUM %, opportunity concentration, and contract coverage.
**Why:** The Portfolio module. CFOs and group-level finance teams use this to see across entities.

### `GET /portfolio/consolidation`
**What:** Cross-entity vendor consolidation opportunities — vendors where different entities are buying from the same supplier without aggregated leverage.
**Why:** Group procurement action — finding where separate BUs could consolidate buying to unlock better pricing.

### `GET /portfolio/vendor-leverage`
**What:** Vendor leverage analysis — showing where the company's total wallet share with a vendor is large enough to negotiate.
**Why:** Strategic procurement insight — prioritizing which supplier relationships to renegotiate first.

### `GET /portfolio/pnl-impact`
**What:** P&L impact summary of identified opportunities by entity.
**Why:** CFO-level view — translating the opportunity pipeline into financial statement impact.

---

## Workflow Automation (Tasks)

### `GET /tasks` · `POST /tasks`
**What:** List and create workflow tasks (e.g., "Review this auto-renewal", "Send challenge letter to Vendor X").
**Why:** The Tasks module. When the Workflow Automation agent identifies a high-priority, time-sensitive opportunity, it creates a task and assigns an owner.

### `GET /tasks/{id}` · `PATCH /tasks/{id}`
**What:** View and update a task.
**Why:** Task management for procurement teams — tracking who is doing what.

### `POST /tasks/{id}/approve` · `POST /tasks/{id}/reject`
**What:** Approve or reject a task that requires human approval before execution.
**Why:** The human-in-the-loop gate for workflow automation. No high-risk action executes without explicit approval.

---

## Advanced Agents & Data Operations

### `POST /anomalies/run-detection` · `GET /anomalies` · `PATCH /anomalies/{id}/review`
**What:** Run anomaly detection (Z-score, IQR, new-vendor flags, duplicate-payment signatures), list anomaly flags, and review/dismiss them.
**Why:** Beyond rule-based detection, this catches statistical outliers — spend spikes, unusual invoice patterns, off-pattern GL coding — that rules wouldn't catch.

### `POST /extraction/run` · `GET /extraction/verification-queue` · `POST /extraction/verify/{id}`
**What:** Run the Contract Extraction agent on a document, view extracted terms pending review, and verify/correct extractions.
**Why:** The Contract Extraction agent reads contracts and extracts terms (renewal dates, indexation clauses, rate cards) but never writes them directly to canonical data. Extracted terms sit in a verification queue for a human to approve. This is the HITL gate for AI-extracted contract data.

### `GET /data-steward/proposals` · `POST /data-steward/run` · `PATCH /data-steward/proposals/{id}`
**What:** Run the Data Steward agent, list its proposals (normalization fixes, mapping gaps), and approve/reject them.
**Why:** The Data Steward monitors data quality and proposes corrections — but any fix that would change a reported figure requires human approval before it's applied.

### `GET /data-steward/metrics`
**What:** Data quality metrics: match coverage %, enrichment coverage, normalization gaps, proposal acceptance rate.
**Why:** Ops and engineering monitoring — how well the automated data pipeline is performing.

---

## Rate Cards & Line Items

### `GET/POST /contracts/{id}/rate-cards` · `GET/PATCH/DELETE /rate-cards/{id}`
**What:** Manage rate cards for contracts (pricing schedules with SKUs, unit prices, and volume tiers).
**Why:** Phase 1.5 capability — enables above-rate detection at the line-item level. When a contract has a rate card and an invoice charges more than the contracted price, that's a recovery opportunity.

### `POST /extract/contracts/{id}/rate-cards`
**What:** AI extraction of rate card data from a contract document.
**Why:** Rate cards are often buried in contract PDFs. This extracts them automatically, subject to human verification.

### `GET /rate-cards/verification-queue` · `POST /rate-cards/{id}/verify`
**What:** Review and verify AI-extracted rate cards before they become canonical.
**Why:** Same HITL pattern as contract extraction — AI does the work, human confirms before it affects financial calculations.

### `POST /line-items/ingest` · `GET /line-items`
**What:** Ingest invoice line items and list them for an invoice.
**Why:** Line-item-level data enables more precise above-rate detection — comparing each invoiced line against the contracted rate for that SKU.

### `POST /line-items/run-detection`
**What:** Run line-item detection rules (above-rate, volume-tier) against a set of invoice line items.
**Why:** The Phase 1.5 detection layer — catching pricing discrepancies at the granular invoice line level rather than just at the header level.

### `POST /line-items/recovery-pack` · `GET /line-items/recovery-pack/{id}`
**What:** Build and retrieve a line-item-level recovery pack.
**Why:** More precise recovery claims — a challenge letter built on line-item evidence is harder to dispute than one based only on invoice totals.

---

## Agent Operations & Learning

### `GET /agent-runs` · `GET /agent-runs/{id}`
**What:** Immutable audit log of every agent run — what agent, what trigger, what inputs/outputs, confidence, whether AI or human, timestamp.
**Why:** Full auditability requirement. Every AI action is logged. Ops teams can replay, investigate, and rollback agent decisions from this log.

### `GET /learning/calibration` · `POST /learning/recalibrate`
**What:** View model calibration state (how well confidence scores match actual accuracy) and trigger recalibration.
**Why:** The continuous learning loop — as humans accept/reject matches and resolve quarantine items, the system recalibrates its confidence scores to improve future matching.

---

## System & Admin

### `GET /health` (and `/health/degradation`)
**What:** System health check; degradation mode status (whether agents and model provider are available).
**Why:** Load balancer health checks; graceful degradation — if the LLM provider is down, the platform still serves analysis from the memory snapshot.

### `GET /admin/quotas/{tenant_id}` · `POST /admin/quotas`
**What:** View and set per-tenant resource quotas (API rate limits, agent run limits, spend volume tiers).
**Why:** Multi-tenant resource governance — prevents one tenant from consuming all resources; enables per-customer capacity management.

### `GET /me`
**What:** Current user profile, roles, and permissions.
**Why:** Used by the frontend to determine what modules and actions to show/hide based on the user's role.

---

## What Is Explicitly Out of Scope (v1)

- **External market benchmarking** — "Are we paying above market?" requires external data. Labeled "requires external data" in the UI.
- **Should-cost modeling** — No external pricing databases.
- **Autonomous supplier communications** — Agents draft; humans always send.
- **Multi-tenant active mode** — Infrastructure exists; dormant for v1 single-workspace product.
