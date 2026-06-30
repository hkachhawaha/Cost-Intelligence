# Terzo Cost Intelligence — Solution Blueprint & Product Architecture

*An AI-agent-driven platform that maps spend to contracts to recover margin and govern commitments*

| **Field**      | **Detail**                                                                                          |
| -------------- | --------------------------------------------------------------------------------------------------- |
| Document       | Cost Intelligence — Comprehensive Solution Blueprint                                                |
| Prepared for   | Terzo (terzo.ai) — Product, Design, Engineering & Leadership                                        |
| Owner          | Himalaya, Product                                                                                   |
| AI Layer       | NirvanaI (conversational + agent layer)                                                             |
| Version        | 1.1 (Draft for review)                                                                              |
| Date           | June 2026                                                                                           |
| Status         | Blueprint for strategy, design, engineering, implementation & roadmap                               |
| Classification | Internal / Confidential                                                                             |
| Data principle | First-party only (spend + contracts + linkage); no external benchmarks unless explicitly integrated |

# Document Control

| **Version** | **Date** | **Author** | **Notes**                                                                                                                                                                                                                     |
| ----------- | -------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0.1         | Jun 2026 | Product    | Initial outline and prototype findings                                                                                                                                                                                        |
| 1.0         | Jun 2026 | Product    | Full blueprint: architecture, agent layer, data model, workflows, security, scalability, roadmap                                                                                                                              |
| 1.1         | Jun 2026 | Product    | Added agent memory operating model (ingest-once), Relationship Intelligence scenarios, Google Sheets ingestion, Invoice intelligence, concrete NFR/roadmap targets, UX-framework adherence, success criteria; NirvanaI naming |
| 2.0         | Jun 2026 | Product    | **Realignment (v2):** product re-scoped to a single-workspace, **Google-Sheets-driven** Cost Intelligence app whose UI matches the `Terzo-Cost-Intelligence-App-v2` prototype; Agent Memory operating model; Relationship Intelligence; NirvanAI ask-the-data + document generation. See §0. |
| [next]    | [date] | [owner]  | [change summary]                                                                                                                                                                                                            |

This document is the controlling reference for the Cost Intelligence platform. It is intended to be a living blueprint; the agent layer, data contracts, and roadmap sections in particular are expected to evolve. Placeholders marked “[ ]” and AGENT HOOK callouts indicate decision points and AI-agent integration surfaces that must be specified during design and implementation.

---

# 0. Realignment (v2) — Google-Sheets-Driven Cost Intelligence

> **This section is authoritative and supersedes the rest of this blueprint wherever they conflict.** The platform is delivered as a **single-workspace** product whose **definitive dashboard UI is `Designs/Terzo-Cost-Intelligence-Dashboard.html`** (the executive, dashboard-first design — it supersedes the earlier `Terzo-Cost-Intelligence-App-v2.html` for layout, navigation, widgets and workflows) and whose **primary data source is a connected Google Sheet**. The deterministic backend built in Phases 0–10 (matching, detection, KPIs, memory) is **reused**; the multi-tenant/Auth0/RLS and ERP-connector machinery remains in the codebase but is **dormant** for this product.

### 0.1 Product shape
A finance/procurement leader connects a Google Sheet (a "Vendor Intelligence Data Package"), and the app maps spend→contracts, links invoices and POs, generates Cost Intelligence insights, and presents them through the prototype's 14 modules with a NirvanAI assistant. No login gate; one workspace; first-party data only.

### 0.2 Google Sheets as the primary data source
- The connected workbook is read via its **public export** (shared "anyone with the link can view") — **no OAuth**. The user pastes a URL in **Settings → Cost Intelligence → Data Source**.
- Reference workbook: **NEXUS COMMUNICATIONS — Vendor Intelligence Data Package** (`1DiOWK243sZaIXOw6ZTYnt3aGLnuZ9DYT0ITQOsWXwxg`), 7 tabs: **Read Me** (skipped), **Contracts**, **Contract Clauses**, **Invoices**, **Purchase Orders**, **Inventory**, **Spend Ledger**. Each tab has a title banner in row 1 and headers in row 2.
- Everything downstream — Contracts, Invoices, Spend, Suppliers, Cost Intelligence metrics, dashboard analytics and AI insights — is powered by this sheet.

### 0.3 Spreadsheet-driven ingestion workflow
On **Connect** (or **Refresh**) the agent: (1) reads all sheets; (2) normalizes the data (type coercion, parsing); (3) builds relationships — **Contract↔Invoice**, **Invoice↔Spend**, and **Contract↔Spend fallback** when invoices are unavailable; (4) generates Cost Intelligence insights; (5) stores processed intelligence in **Agent Memory**. Until Refresh is run again, the app keeps serving the existing memory snapshot.

### 0.4 Agent Memory operating model (ingest-once)
Processed intelligence — the normalized dataset, the relationship graph, the ranked opportunities and the KPIs — is stored as a **versioned snapshot** (durable in Postgres, warm in Redis). The app and NirvanAI **operate from memory, never from the live sheet**. A manual **Refresh** re-reads the sheet, rebuilds relationships, recalculates insights, writes a new memory version, and repopulates the dashboards.

### 0.5 Relationship mapping
- **Contract ↔ Invoice** — invoice `Contract_ID`.
- **Invoice ↔ Spend** — spend `Invoice_Reference`, else PO, else contract.
- **Contract ↔ Spend (fallback)** — a confidence-ranked ladder: **Contract-ID → PO → vendor-exact → vendor-fuzzy → unmatched (maverick)**. Every figure inherits the confidence of the link beneath it.

### 0.6 Cost Intelligence insights (grounded in the connected data)
Deterministic detection over the normalized data — **maverick spend, overspend vs annual value, spend after expiry, duplicate payment, silent auto-renewal, unused commitment, unclaimed rebate** (from clause text), **off-rate billing** (pricing-schedule clause vs invoice unit price), and **license shelfware** (inventory utilization). Each opportunity carries an impact $, confidence, rationale, formula, recommended action and spend evidence. No LLM computes a figure.

### 0.7 NirvanAI conversational experience
NirvanAI answers questions and drafts negotiation documents **deterministically from Agent Memory** (first-party only): ask-the-data (where can I save the most, what auto-renews, what's recoverable, consolidation candidates, expiring contracts, commitments…) and document generation (renegotiation email, non-renewal notice, supplier challenge letter, RFP brief, supplier SWOT). Benchmark/should-cost questions are out of scope ("requires external data"). It is available as a global slide-out on every module and as a dedicated module.

### 0.8 Dashboard outputs (executive, dashboard-first — `Terzo-Cost-Intelligence-Dashboard.html`)
A **dashboard-first, hub-and-drill** experience organised into five nav groups:
- **Overview** — **Home** (greeting, "we found money" hero with recover/save/recovered chips, a spend-under-management ring, off-contract exposure, top-4 action cards, a spend-by-category donut, and an attention/alerts panel) · **Opportunities** (filter chips + ranked opportunity cards with expandable formula/evidence/action).
- **Analyze** — **Analyze** hub (AI-generated insights, spend trend, supplier performance, utilisation, variance) · **Spend** · **Contracts** (card/table toggle → full **contract drill-down** page: KPIs, overview, commitment ring, AI insights, recovery, related invoices/spend) · **Vendors** (concentration + risk) · **Indexation & Exposure**.
- **Act** — **Act** hub (actions grouped by recommended-action category) · **Margin Recovery** (per-vendor packs + draft challenge letter) · **Renewals** · **Commitments** · **Commitment Check**.
- **Intelligence** — **Intelligence** hub (NirvanAI copilot hero, AI findings/anomalies, top recommendations) · **Portfolio** (entity rollups, group mix, scorecards).
- **System** — **Data Quality** (match-coverage donut, unmatched queue, fuzzy links) · **Settings** (**Data Source configuration** + assumptions).

The visual system (rounded cards, gradient hero/KPI tiles, ring/donut/bar charts, opportunity cards, the slide-out NirvanAI panel and the "✦ Ask NirvanaI" button) matches the dashboard prototype. Every screen reads the Agent Memory snapshot; "Draft with NirvanaI" generates documents into the chat.

### 0.9 What changed vs Phases 0–10
- **Single workspace, no Auth0/RLS gate** for the running product (multi-tenant infra retained, dormant).
- **Google Sheet is the source** (the ERP connectors and staged ingestion remain available but are not the primary path).
- **UI re-platformed** to match the prototype (`apps/web/app/ci`).
- **Reused as-is:** deterministic detection rules, KPI computation, the memory concept, and the determinism-for-money guarantee.

# Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. Product Vision & Strategy](#2-product-vision-strategy)
- [3. Solution Overview](#3-solution-overview)
- [4. Capability Modules](#4-capability-modules)
- [5. AI Agent Layer (Blueprint)](#5-ai-agent-layer-blueprint)
- [6. Architecture](#6-architecture)
- [7. Data Model](#7-data-model)
- [8. Workflows](#8-workflows)
- [9. User Journeys & Personas](#9-user-journeys-personas)
- [10. Integrations](#10-integrations)
- [11. Analytics & Intelligence](#11-analytics-intelligence)
- [12. Security, Privacy & Compliance](#12-security-privacy-compliance)
- [13. Scalability & Performance](#13-scalability-performance)
- [14. Operational Considerations (DevOps / MLOps / AgentOps)](#14-operational-considerations-devops-mlops-agentops)
- [15. Roadmap](#15-roadmap)
- [16. Risks & Mitigations](#16-risks-mitigations)
- [17. Appendices](#17-appendices)

# 1. Executive Summary

Cost intelligence is the capability of turning an organization’s own cost data — what it committed to in contracts and what it actually spent — into ranked, dollar-quantified, actionable savings and risk signals. Terzo is uniquely positioned to deliver it because the platform already owns both halves of the equation: a structured contract record (95+ fields including ACV/TCV, renewal type, uplift, yearly commitments and SKU-level rate cards) and a first-class spend record fed from ERP/P2P systems (Coupa, Oracle, SAP) carrying vendor, amount, GL code, cost center, PO and source system.

The platform maps spend back to its governing contract and surfaces leakage and savings: off-contract (maverick) spend, overspend versus committed value, unused commitments, above-rate payments, silent auto-renewals, uplift creep, post-expiry spend and duplicate invoices. On a representative synthetic dataset ($1.69M of spend across 10 contracts), the working prototype identified ~$241K of opportunity — split into recoverable cash and recurring savings — at 94.9% spend-to-contract match coverage.

This blueprint extends that validated prototype into a real-world product with an AI agent layer that can ingest, interpret, enrich and act on data from multiple sources. Throughout the document, AGENT HOOK callouts mark exactly where autonomous and human-in-the-loop agents participate: data ingestion, intelligence generation, anomaly detection, recommendations, workflow automation and user assistance (the NirvanaI assistant).

A defining architectural choice is ingest-once, operate-from-memory: the agent reads each source a single time, establishes the relationships across the three core datasets — Contracts, Invoices and Spend Transactions — generates intelligence, and persists the result to a dedicated memory layer that serves as the system of intelligence. The platform then answers from this cached intelligence rather than repeatedly re-querying source systems, refreshing only on demand — sharply improving performance and reducing source-system dependency. Initial data sources are spreadsheet-based (Google Sheets first), with CSV, Excel, ERP and API integrations to follow.

The strategic wedge is first-party integrity: every figure is provable against the customer’s own contracts and invoices, with no dependency on external market-benchmark data. That makes the product defensible across all spend categories and faster to value than services-led or benchmark-network competitors, while leaving a clear, optional path to add external intelligence later.

### Headline outcomes the platform targets

- **Recover margin** — find and package overbilling, duplicates and post-expiry spend for supplier challenge

- **Prevent leakage** — flag silent auto-renewals, uplift creep and unused commitments before money is lost

- **Govern commitments** — validate a deal’s exposure before signature (Commitment Check / control layer)

- **Compress cycle time** — AI agents do the ingestion, matching, detection and first-draft action, with humans approving

# 2. Product Vision & Strategy

## 2.1 Problem & opportunity

Enterprises sign contracts that define what they should pay, then pay invoices that drift from those terms over time. ERP systems record what happened and spend analytics explains it, but few systems continuously validate actual spend against contracted terms — and almost none govern a commitment before it executes. The result is recurring, quantifiable margin leakage that is invisible until it has already flowed through the P&L.

Compounding this, contract data, invoice data and spend-transaction data typically live in separate systems; the relationships between them are hard to identify; business users reconcile them manually; and reporting tools show only static views. Enterprise customers such as Cisco require an intelligent system that understands the relationships across contracts, invoices and spend, generates real-time insight, surfaces cost-optimization opportunities, and provides conversational access to procurement intelligence.

## 2.2 Vision & mission

Vision: every dollar an enterprise spends is continuously reconciled against what it agreed to pay, and every new commitment is validated before it is signed.

Mission: give finance, procurement and legal teams an AI-driven system of intelligence that detects leakage, recovers margin, and governs commitments — grounded entirely in their own data.

## 2.3 Value proposition & differentiation

Terzo’s defensible position is the spend-to-contract join performed on first-party data. Cloud-cost (FinOps) tools rely on usage telemetry; procurement spend-analytics suites and SaaS-spend tools lean on external benchmark networks; most CLM tools never ingest a dollar of actual spend. Terzo already holds both datasets live and can reconcile them across every category without external data.

> **◉ AGENT HOOK — Intelligence generation**
>
> Detection agents continuously recompute the savings/recovery catalog as new spend lands, so the value proposition is always evidenced by current data rather than a periodic report.
>
> *Autonomy: L2 (acts, logs, reversible) Human-in-the-loop: No (read-only analysis)*

## 2.4 Target users & personas

| **Persona**                 | **Primary goal**                    | **Key jobs in the product**                               |
| --------------------------- | ----------------------------------- | --------------------------------------------------------- |
| CFO / Finance leader        | Protect margin; trust the numbers   | Portfolio view, realized vs. identified savings, exposure |
| CPO / Procurement leader    | Prioritize savings; manage renewals | Opportunity Assessment, Renewals, Vendors, consolidation  |
| Category / Sourcing manager | Run sourcing events                 | Spend Explorer, RFP drafts, supplier SWOT                 |
| AP / Finance analyst        | Recover cash; clean data            | Margin Recovery, Data Quality, duplicate/post-expiry      |
| Legal / Contract owner      | Manage terms & risk                 | Contracts, Indexation, auto-renewal & uplift exposure     |

## 2.5 Business model & pricing (placeholder)

[Pricing model to be defined.] Candidate models: platform subscription tiered by spend-under-management; value-share on realized recovery; module-based packaging (Recovery, Control Layer, Portfolio). Pricing experiments and willingness-to-pay analysis are out of scope for this blueprint and should be run separately.

## 2.6 Success metrics / North Star

Proposed North Star: realized savings & recovery as a percentage of spend under management. Supporting input metrics:

- **Spend under management** — % of spend linked to an active contract

- **Identified opportunity** — $ and % of spend flagged, by bucket (savings vs. recovery)

- **Realization rate** — identified → in-progress → recovered conversion

- **Match coverage & confidence** — quality of the spend↔contract join underpinning every figure

- **Cycle time** — detection → action, and agent-assisted vs. manual

### Success criteria

The platform is successful when:

- Users can query cost intelligence in natural language via NirvanaI.

- The AI agent operates primarily from memory rather than re-querying source data.

- Contract, Invoice and Spend relationships are established automatically.

- Cost-optimization opportunities are surfaced proactively.

- The shipped UI faithfully replicates the approved Terzo Cost Intelligence prototype.

# 3. Solution Overview

## 3.1 What it is

Cost Intelligence is a multi-module web application plus an AI agent layer and a conversational assistant (NirvanaI). It ingests the three core datasets — Contracts, Invoices and Spend Transactions — starting with Google Sheets (CSV, Excel, ERP and API to follow), links them, stores the reconciled result in a dedicated memory layer, detects leakage and savings, drafts and automates the resulting actions, and governs new commitments — all on a shared, event-driven data platform.

## 3.2 Core capabilities

| **Module**             | **What it does**                               | **Primary value**                         |
| ---------------------- | ---------------------------------------------- | ----------------------------------------- |
| Dashboard              | KPIs, alerts, opportunity-by-type              | At-a-glance health & leakage              |
| Opportunity Assessment | EBITDA-style ranking + decision sprint         | Prioritized 'act first' plan              |
| Spend Explorer         | Categorized spend, taxonomy, filters           | Visibility by vendor/category/cost center |
| Contracts              | Register, terms, utilization, indexation       | The contractual 'should'                  |
| Vendors                | Supplier rollup, consolidation candidates      | Leverage & rationalization                |
| Indexation & Exposure  | Index/COLA-linked contracts & modeled exposure | Forward cost-risk visibility              |
| Margin Recovery        | Recovery packs for supplier challenge          | Recoverable cash                          |
| Renewals               | Calendar, auto-renewal & uplift exposure       | Act before deadlines                      |
| Commitment Check       | Pre-signature stress test & verdict            | Govern new commitments                    |
| Portfolio              | Multi-entity rollup                            | Group-level visibility & control          |
| NirvanaI               | Ask-the-data + document generation             | Conversational analysis & drafting        |
| Data Quality           | Match confidence, unmatched queue              | Trust & transparency                      |

## 3.3 Conceptual architecture

![](assets/media/image1.png)

*Figure 1. Layered conceptual architecture — the AI agent layer sits between the data platform and the application modules, with human-in-the-loop control.*

## 3.4 First-party data principle & scope boundary

The platform’s integrity rests on a hard scope boundary: analysis uses only spend records, contract records and the linkage between them. Capabilities that require external data — “you’re paying above market rate”, peer benchmarking, should-cost modeling, or judging whether an uplift is fair versus CPI — are explicitly out of scope for v1 and surfaced in the UI as “requires external data”. The architecture leaves a clean, optional integration seam to add such intelligence later without compromising the first-party guarantee.

# 4. Capability Modules

Each module is a view onto the same reconciled dataset and shares the agent layer. The table summarizes the module surface; agent participation is noted inline and detailed in Section 5.

| **Module**             | **Key features**                                                            | **Agents involved**                  |
| ---------------------- | --------------------------------------------------------------------------- | ------------------------------------ |
| Dashboard              | KPI tiles (SUM, compliance, PO coverage), alerts, opportunity-by-type chart | Detection, Anomaly, Assistant        |
| Opportunity Assessment | Top-N by impact×confidence, 4-week sprint plan                              | Detection, Recommendation            |
| Spend Explorer         | L1/L2 taxonomy, vendor/category/cost-center filters, trends                 | Enrichment, Anomaly                  |
| Contracts              | Terms, utilization bars, indexation, linked spend                           | Contract Extraction, Matching        |
| Vendors                | Canonical rollup, consolidation candidates                                  | Enrichment, Recommendation           |
| Indexation & Exposure  | Index/COLA register, exposure slider                                        | Contract Extraction, Detection       |
| Margin Recovery        | Recovery packs, challenge letters, status workflow                          | Detection, Document/Action, Workflow |
| Renewals               | Calendar, notice-deadline urgency, uplift exposure                          | Detection, Workflow, Assistant       |
| Commitment Check       | Stress test ±5/10/15%, approve/condition/block                              | Commitment Control                   |
| Portfolio              | By-entity spend, SUM, opportunity                                           | Detection, Recommendation            |
| NirvanaI               | Ask-the-data, document generation                                           | Assistant, Document/Action           |
| Data Quality           | Match confidence, unmatched & fuzzy queues                                  | Matching, Data Steward               |

> **◉ AGENT HOOK — User assistance**
>
> The NirvanaI assistant is available on every module. It answers natural-language questions from first-party data (e.g. “what auto-renews this quarter?”) and drafts documents (renegotiation email, non-renewal notice, recovery letter, RFP brief, supplier SWOT).
>
> *Autonomy: L1–L2 (answers; drafts await human send) Human-in-the-loop: Yes (human reviews/sends all drafts)*

# 5. AI Agent Layer (Blueprint)

The agent layer is the operational core of the product. It is a network of specialized agents coordinated by an orchestrator, each responsible for a stage of the ingest → interpret → enrich → detect → recommend → act loop. Agents are deterministic where determinism matters (matching, rule evaluation, financial math) and generative where judgment or language is required (classification, extraction, drafting, conversation).

## 5.1 Autonomy model

| **Level**             | **Definition**                                | **Example**                            |
| --------------------- | --------------------------------------------- | -------------------------------------- |
| L0 — Suggest          | Proposes; human does everything               | Recommends a renegotiation target      |
| L1 — Draft            | Produces an artifact; human reviews & sends   | Drafts the supplier challenge letter   |
| L2 — Act (reversible) | Executes low-risk, logged, reversible actions | Re-runs matching; opens an opportunity |
| L3 — Act (gated)      | Executes higher-risk actions behind approval  | Files a workflow task; posts an alert  |

No agent takes an irreversible external action (e.g. sending a letter to a supplier, cancelling a contract) without explicit human approval. Autonomy levels are configurable per tenant and per agent.

## 5.2 Agent architecture

![](assets/media/image2.png)

*Figure 2. Agent orchestration — specialized agents around an orchestrator, on shared services (model gateway, vector/memory store, tool registry, guardrails, eval/audit).*

## 5.3 Agent catalog

The catalog below specifies each agent. Triggers, inputs and outputs are indicative and must be finalized against the data contracts in Section 7 and the integration framework in Section 10.

| **Agent**            | **Role**                                                     | **Triggers**                        | **Inputs → Outputs**                       | **Autonomy / HITL**   |
| -------------------- | ------------------------------------------------------------ | ----------------------------------- | ------------------------------------------ | --------------------- |
| Ingestion            | Land, validate, dedupe source data                           | Source webhook, schedule, file drop | Raw feeds → validated staged records       | L2 / no               |
| Enrichment           | Normalize vendors, currency, GL; classify to taxonomy        | New staged records                  | Staged → canonical, categorized records    | L2 / spot-check       |
| Matching             | Link spend↔contract (PO-first, then fuzzy), score confidence | New/changed spend or contract       | Records → MatchResults + unmatched queue   | L2 / review low-conf  |
| Contract Extraction  | Extract terms, clauses, index/COLA, rate cards               | New/updated contract document       | Document → structured contract fields      | L1 / verify extracted |
| Detection            | Run the leakage/savings rule engine                          | Post-match, schedule                | Reconciled data → Opportunities + $ impact | L2 / no               |
| Anomaly              | Flag outliers, spikes, new patterns                          | Streaming spend, schedule           | Spend series → anomaly flags               | L1 / review           |
| Recommendation       | Rank opportunities; advise next action                       | New/updated opportunities           | Opportunities → ranked actions + rationale | L1 / no               |
| Document/Action      | Draft letters, RFPs, SWOTs, memos                            | User or workflow request            | Context → editable document draft          | L1 / human sends      |
| Workflow Automation  | Create tasks, route approvals, notify                        | Opportunity status, thresholds      | Action → tasks, assignments, alerts        | L3 / gated            |
| Commitment Control   | Stress-test a proposed commitment                            | Commitment Check request            | Deal terms → exposure + verdict            | L1 / human decides    |
| Assistant (NirvanaI) | Conversational Q&A and drafting                             | User message                        | Question → grounded answer / draft         | L1–L2 / yes           |
| Data Steward         | Monitor quality, reconcile, surface gaps                     | Schedule, data-quality events       | Data → quality metrics, fix proposals      | L1 / approve fixes    |

## 5.4 Orchestration & memory

The orchestrator decomposes tasks, routes them to agents, maintains run state, and enforces human-in-the-loop gating. Shared memory comprises: short-term run context; a vector store of contracts, clauses and prior interactions for retrieval-augmented reasoning; and a structured store of canonical entities. Every agent run writes an immutable AgentRun/AuditEvent record (Section 7) capturing inputs, outputs, confidence and whether the actor was AI or human.

> **◉ AGENT HOOK — Workflow automation**
>
> On a high-confidence, time-sensitive opportunity (e.g. an auto-renewal inside its notice window), the Workflow agent can open a task, assign an owner, and schedule a reminder — then hand a drafted notice to the Document agent. The external action (sending the notice) remains human-gated.
>
> *Autonomy: L3 (gated) Human-in-the-loop: Yes (approval before external send)*

## 5.5 Model strategy & gateway

All model calls flow through a model gateway that handles provider/model routing, version pinning, caching, cost and rate control, and PII redaction. The platform standardizes on **Google Gemini**: `gemini-2.5-pro` for the strong general model (extraction, drafting, conversation) and `gemini-2.5-flash` for smaller/cheaper classification and routing, with `gemini-embedding-001` for embeddings — and deterministic code (not models) for financial math and rule evaluation.

## 5.6 Guardrails, safety & evaluation

- **Groundedness** — answers and drafts must cite the underlying spend/contract records; no fabricated figures

- **Determinism for money** — all $ math runs in code, not in a model; models never compute savings

- **Prompt-injection defense** — contract/document text is treated as untrusted input; tool use is allowlisted

- **Confidence thresholds** — low-confidence results route to human review rather than auto-action

- **Evaluation** — golden datasets and regression evals for extraction accuracy, match precision/recall, and answer faithfulness

- **Auditability** — every AI action is logged with inputs, outputs and actor for review and rollback

## 5.7 Human-in-the-loop framework

Each agent declares the actions it may take autonomously versus those requiring approval. The UI exposes a review queue for low-confidence matches, extracted terms, and any external action. Tenants can tighten or relax autonomy per agent. The objective is maximal automation of analysis and drafting, with humans retained as the decision-makers for anything that leaves the system.

## 5.8 Agent memory & operating model

A defining design principle is ingest-once, operate-from-memory. On first ingestion (the initial sync) the agent reads each source, establishes Contract ↔ Invoice ↔ Spend relationships, generates intelligence (opportunities, scores, summaries) and persists the result to a dedicated memory layer that acts as the system of intelligence.

![](assets/media/image3.png)

*Figure 3. Agent memory — an initial sync builds relationships and intelligence into a memory store; the agent then operates from memory until an explicit Refresh.*

### Initial sync

Reads source data, creates relationships, generates intelligence, and stores results in memory.

### Operational mode

After the initial sync the agent operates primarily from memory with no live source-system dependency — enabling near-instant analysis and lower load on source systems.

### Refresh

From Settings → Data Sources, a Refresh Data action re-reads the source, recomputes relationships, updates memory and regenerates intelligence. Until refresh is run, the agent continues operating on existing memory.

> **◉ AGENT HOOK — Data ingestion (memory-first)**
>
> The Ingestion and Relationship agents run on the initial sync and on each explicit Refresh — not on every query — caching reconciled intelligence so the platform avoids repeated source processing.
>
> *Autonomy: L2 (acts, logs, reversible) Human-in-the-loop: Refresh is user-initiated*

# 6. Architecture

## 6.1 Logical layers

The platform is organized into eight layers (Figure 1): source systems; ingestion & integration; data platform; AI agent layer; intelligence & analytics; application/capability modules; presentation; and users. Data flows up; actions flow down. The agent layer is the connective tissue that turns raw data into reconciled intelligence and intelligence into action.

## 6.2 Component responsibilities

| **Component**         | **Responsibility**                                                     |
| --------------------- | ---------------------------------------------------------------------- |
| Connector framework   | Source auth, scheduled/streamed pulls, schema validation, idempotency  |
| Canonical data store  | System of record for vendors, contracts, spend, matches, opportunities |
| Data lake / warehouse | High-volume spend history; analytical queries                          |
| Vector / memory store | Embeddings of contracts/clauses & interactions for agent retrieval     |
| Event bus             | Decouples ingestion, matching, detection and agent tasks               |
| Agent runtime         | Orchestrator + agent workers; queue-backed and async                   |
| Model gateway         | LLM routing, caching, cost/rate control, redaction                     |
| Application services  | Module APIs, auth, business logic                                      |
| Presentation          | Web app, NirvanaI assistant, public/partner APIs                       |

## 6.3 Event-driven design

Ingestion, matching, detection and agent work are decoupled via an event bus. New or changed records publish events; downstream agents subscribe and process incrementally. This yields near-real-time reconciliation, natural back-pressure handling at high volume, and a clean audit trail of what changed and when.

## 6.4 Technology stack (placeholders)

| **Layer**          | **Candidate technology (to confirm)**                                    |
| ------------------ | ------------------------------------------------------------------------ |
| Ingestion/eventing | [stream platform, e.g. Kafka/Kinesis], [workflow/queue]              |
| Data stores        | [OLTP], [warehouse/lakehouse], [object store], [vector DB]       |
| Agent runtime      | [agent framework / orchestration], [serverless or container workers] |
| Models             | Google Gemini via gateway (`gemini-2.5-pro`, `gemini-2.5-flash`), Gemini embeddings (`gemini-embedding-001`) |
| Application        | [API framework], [web framework]                                     |
| Infra              | [cloud], [IaC], [container orchestration], [observability stack] |

## 6.5 End-to-end pipeline

![](assets/media/image4.png)

*Figure 4. Ingestion → intelligence → action pipeline with agent stages, a learning feedback loop, and human-in-the-loop checkpoints.*

# 7. Data Model

## 7.1 Entity-relationship overview

![](assets/media/image5.png)

*Figure 5. Core data model — vendors, contracts (and line items, clauses), spend, invoices, match results, opportunities, recovery items, entities, users, actions, and the AgentRun/AuditEvent log.*

## 7.2 Core entities

### Contract

| **Field**                             | **Type** | **Notes**                     |
| ------------------------------------- | -------- | ----------------------------- |
| contract_id                          | PK       | Canonical contract identifier |
| vendor_id                            | FK       | Owning vendor                 |
| entity_id                            | FK       | Legal entity / BU             |
| acv / tcv                             | money    | Annual / total contract value |
| start / end / effective               | date     | Term boundaries               |
| renewal_type                         | enum     | Auto-renewal / Option / None  |
| renewal_notice_days                 | int      | Notice window                 |
| uplift / index_type / indexed_share | mixed    | Escalation terms & exposure   |
| yearly_commit                        | money    | Committed volume (nullable)   |
| payment_term_days                   | int      | Net terms                     |

### SpendRecord

| **Field**                 | **Type** | **Notes**                           |
| ------------------------- | -------- | ----------------------------------- |
| spend_id                 | PK       | Spend line identifier               |
| vendor_id / contract_id | FK       | Vendor; matched contract (nullable) |
| amount / currency         | money    | Transaction value                   |
| spend_date               | date     | Posting date                        |
| gl_code / cost_center   | string   | Chart-of-accounts segments          |
| po_number                | string   | Primary deterministic match key     |
| source_system            | enum     | Coupa / Oracle / SAP / …            |

### Opportunity & AgentRun

| **Entity**            | **Key fields**                                                                            | **Purpose**                                       |
| --------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Opportunity           | opp_id, contract_id, type, bucket (savings/recovery), impact, confidence, status, owner | A detected, quantified, trackable finding         |
| MatchResult           | match_id, spend_id, contract_id, method, confidence, discrepancies                     | Evidence & confidence of each spend↔contract link |
| RecoveryItem          | rec_id, opp_id, amount, evidence, status                                                | Packaged recoverable for supplier challenge       |
| AgentRun / AuditEvent | run_id, agent, trigger, inputs/outputs ref, confidence, actor (AI/human), timestamp      | Immutable record of every AI/human action         |

## 7.3 Canonical IDs, lineage & data contracts

Vendor normalization produces a canonical vendor_id that folds name variants together; matching uses it as a fallback when PO numbers are missing. Every derived record (MatchResult, Opportunity) carries lineage back to the source spend lines and contract fields that produced it, so any figure can be drilled to its evidence. Each source integration is governed by a versioned data contract (expected fields, types, freshness, volume) enforced by the Ingestion agent.

> **◉ AGENT HOOK — Data ingestion**
>
> The Ingestion agent validates each batch against its data contract, quarantines records that fail, deduplicates, and emits 'records.landed' events. Schema drift raises a data-quality event for the Data Steward agent rather than silently corrupting downstream intelligence.
>
> *Autonomy: L2 Human-in-the-loop: Review on contract violation / drift*

# 8. Workflows

## 8.1 Ingestion to insight

See the ingestion pipeline figure in Section 6.5. Source data is landed and validated, normalized and classified, matched to contracts, then evaluated by the detection and anomaly engines. Resulting opportunities are ranked, drafted into actions, and routed for automation or human approval. Outcomes feed a learning loop that improves scoring and matching over time.

## 8.2 Spend↔contract matching

1.  Deterministic PO match: spend.po_number → contract PO (highest confidence).

2.  Fuzzy fallback: normalized vendor + cost center + amount/date similarity, with a confidence score.

3.  Unmatched bucket: spend with no acceptable match is surfaced as maverick exposure, never hidden.

4.  Confidence propagation: every downstream opportunity inherits the confidence of its underlying match.

> **◉ AGENT HOOK — Anomaly detection**
>
> Beyond rule-based detection, the Anomaly agent watches spend streams for spikes, new vendors, off-pattern GL coding and duplicate-payment signatures, raising flags that become opportunities or data-quality items.
>
> *Autonomy: L1 Human-in-the-loop: Yes (review before action)*

### Relationship intelligence — matching scenarios

![](assets/media/image6.png)

*Figure 6. Relationship matching scenarios — full chain, invoice-missing (AI inference), and many-to-many confidence-based matching.*

The engine links Contract → Invoice → Spend using Contract ID, PO Number, Invoice Number, Supplier, Cost Center, Business Unit and other configurable keys.

5.  Scenario 1 — Contract, Invoice and Spend all present → Contract → Invoice → Spend.

6.  Scenario 2 — Invoice missing → Contract → Spend, inferred via AI matching.

7.  Scenario 3 — Multiple contracts, invoices and spend → confidence-based matching across candidates.

## 8.3 Opportunity lifecycle

![](assets/media/image7.png)

*Figure 7. Opportunity lifecycle — detected → triaged → in progress → realized/recovered, with a dismissed path; agents enrich and draft at every transition.*

## 8.4 Margin recovery workflow

8.  Detection/Anomaly agents identify recoverable items (duplicates, post-expiry, overspend).

9.  Items are grouped per vendor into a recovery pack with evidence and a total.

10. Document agent drafts a supplier challenge letter / debit memo.

11. Human reviews and sends; status moves to in-progress, then recovered when credited.

12. Data Steward proposes a root-cause control (e.g. 3-way match) to prevent recurrence.

## 8.5 Renewal & auto-renewal workflow

The Detection agent computes each contract’s notice deadline (end date minus notice days) and flags auto-renewals inside the look-ahead window, quantifying negotiable uplift. The Workflow agent opens a time-boxed task; the Document agent drafts a renegotiation or non-renewal notice; the human decides and sends.

## 8.6 Commitment check / pre-signature control

Before a new commitment is signed, the Commitment Control agent models indexed exposure (value × index-linked share × adverse move) and stress-tests ±5/10/15%, returning an approve / condition / block verdict against a configurable margin tolerance. The index move is a first-party assumption, not an external feed; the verdict is advisory and the human signs off.

> **◉ AGENT HOOK — Recommendations**
>
> For each opportunity the Recommendation agent produces a ranked next action with rationale and an estimated value, and pre-selects the right document template for the Document agent — turning a finding into a one-click drafted action.
>
> *Autonomy: L1 Human-in-the-loop: No (advice only)*

# 9. User Journeys & Personas

The platform serves several roles against the same reconciled data. Representative journeys:

### CFO — quarterly margin review

13. Opens Portfolio: spend under management, identified vs. realized savings by entity.

14. Asks NirvanaI “where is the biggest exposure this quarter?”

15. Drills into the top opportunities; assigns owners; tracks realization.

### Procurement lead — renewal & sourcing

16. Reviews Renewals calendar sorted by urgency; sees uplift exposure.

17. For an auto-renewal in window, generates a non-renewal/renegotiation draft via NirvanaI.

18. Launches a sourcing event for a fragmented category using an auto-drafted RFP brief.

### AP / finance analyst — recovery

19. Opens Margin Recovery; reviews recovery packs per vendor.

20. Generates the challenge letter; sends after review; marks items recovered as credits arrive.

21. Confirms a prevention control with the Data Steward agent.

| **Persona**  | **Entry point**        | **“Aha” moment**                        |
| ------------ | ---------------------- | --------------------------------------- |
| CFO          | Portfolio / Dashboard  | Provable savings without external data  |
| Procurement  | Renewals / Assessment  | Acting before an auto-renewal locks in  |
| Category mgr | Spend Explorer         | Fragmented category → one-click RFP     |
| AP analyst   | Margin Recovery        | Recoverable cash packaged automatically |
| Legal        | Contracts / Indexation | Index exposure quantified per contract  |

## 9.1 Experience requirements

The shipped product must follow the Terzo Design System, the approved Terzo Cost Intelligence prototype, the Terzo Dashboard Framework and the NirvanaI Experience Framework. No deviations are permitted without product approval.

# 10. Integrations

## 10.1 Integration patterns

- **Spreadsheets / files** — Google Sheets (the initial ingestion path), CSV and Excel

- **API** — real-time/scheduled pulls from ERP/P2P/CLM systems

- **Event/stream** — near-real-time spend ingestion at volume

- **Flat-file / CSV** — bulk import and systems without APIs

- **Webhooks** — change notifications from source systems

## 10.2 Source & destination systems

| **Direction** | **System class**             | **Examples**                                         |
| ------------- | ---------------------------- | ---------------------------------------------------- |
| Inbound       | Spreadsheet / file (initial) | Google Sheets (first), CSV, Excel                    |
| Inbound       | ERP / P2P                    | SAP, Oracle, Coupa, NetSuite, Workday                |
| Inbound       | CLM / contracts              | Terzo contract module, external CLM, document stores |
| Inbound       | AP / invoices                | AP automation, invoice feeds                         |
| Inbound       | Identity                     | SSO / SAML / SCIM                                    |
| Outbound      | Collaboration                | Slack / Teams / email notifications                  |
| Outbound      | BI / export                  | Warehouse sync, CSV/PDF export, dashboards           |

## 10.3 Connector framework

A connector framework standardizes auth, scheduling, schema mapping, idempotency and retries. Each connector declares a data contract; the Ingestion agent enforces it. New sources are added without changing downstream intelligence, because everything resolves to the canonical model.

> **◉ AGENT HOOK — Data ingestion (multi-source)**
>
> Ingestion agents run per connector, mapping heterogeneous source schemas to the canonical model, reconciling currencies and calendars, and emitting normalized events. [Connector-specific field mappings to be defined per source system.]
>
> *Autonomy: L2 Human-in-the-loop: Review on mapping ambiguity*

# 11. Analytics & Intelligence

## 11.1 Detection rule catalog

| **Opportunity**          | **Trigger**                              | **Bucket**         |
| ------------------------ | ---------------------------------------- | ------------------ |
| Maverick / off-contract  | Spend with no acceptable contract match  | Savings            |
| Unused commitment        | Actual < committed beyond threshold     | Savings            |
| Overspend vs ACV         | Matched spend > ACV beyond threshold    | Recovery           |
| Silent auto-renewal      | Auto-renew within notice window          | Savings            |
| Uplift creep             | Renewal uplift > 0 (quantified)         | Savings            |
| Spend after expiry       | Spend dated after contract end           | Recovery           |
| Duplicate invoice        | Same invoice paid more than once         | Recovery           |
| Above-rate (Phase 1.5)   | Invoice unit price > contracted rate    | Recovery           |
| Missing invoice          | Spend / PO with no corresponding invoice | Control            |
| Unpaid / overdue invoice | Invoice past due and unpaid              | Control            |
| Invoice anomaly          | Outlier amount or off-pattern invoice    | Recovery / Control |

## 11.2 Scoring & ranking

Each opportunity carries a dollar impact (transparent formula) and a confidence derived from match quality and rule certainty. Ranking is impact × confidence, with effort and time-sensitivity as secondary factors. Maverick savings use a configurable recapture-rate parameter; all other figures derive directly from the data.

## 11.3 KPIs, forecasting & reporting

- KPIs: spend under management, contract compliance, PO coverage, identified vs. realized, recoverable.

- Forecasting: renewal and indexed-exposure projections from contract terms (first-party).

- Reporting: per-entity portfolio rollups; export to BI/warehouse.

> **◉ AGENT HOOK — Intelligence generation (continuous)**
>
> Detection and Recommendation agents recompute opportunities and rankings on every relevant data change, keeping the dashboard, assessment and alerts current without batch reporting cycles.
>
> *Autonomy: L2 Human-in-the-loop: No*

External boundary: market benchmarking and should-cost remain out of scope until an external data source is explicitly integrated; the UI labels such asks as “requires external data”.

# 12. Security, Privacy & Compliance

![](assets/media/image8.png)

*Figure 8. Trust zones and controls from customer source systems through tenant-isolated data and the application to AI governance and users.*

## 12.1 Identity & access

SSO/SAML with SCIM provisioning; role-based and attribute-based access control scoped by entity; least-privilege source credentials; full audit of access and actions.

## 12.2 Tenancy, encryption & data protection

Per-tenant data segregation with row-level isolation and per-tenant encryption keys; encryption in transit (TLS 1.2+) and at rest; DLP and key rotation; configurable data-residency options.

## 12.3 AI governance

- Model/version pinning and a governed model gateway with PII redaction.

- Prompt-injection defenses; untrusted document text is sandboxed; allowlisted tools.

- Confidence thresholds and human approval for any external action.

- Red-team / jailbreak testing; groundedness checks; no training on customer data without consent.

- Immutable audit log of every AI and human action (AgentRun/AuditEvent).

## 12.4 Compliance posture

Target posture: SOC 2 Type II and ISO 27001; GDPR/CCPA alignment; HIPAA-ready handling where applicable. [Certification timeline to be confirmed.]

> **◉ AGENT HOOK — User assistance (governed)**
>
> The Assistant answers strictly from data the requesting user is authorized to see; access control is enforced before retrieval, and every answer is traceable to its sources.
>
> *Autonomy: L1 Human-in-the-loop: N/A (read-only, access-scoped)*

# 13. Scalability & Performance

![](assets/media/image9.png)

*Figure 9. Reference runtime — multi-tenant SaaS with autoscaled services, an event bus, async ingestion/matching/agent workers, partitioned data stores, and AgentOps observability.*

## 13.1 Volume assumptions

The platform is designed for enterprise scale: 10M+ spend transactions, 1M+ invoices and 500K+ contracts per tenant, with spend landing continuously. Agent workloads scale with change volume rather than total data size, because processing is incremental, event-driven and served from the cached memory layer.

## 13.2 Performance & reliability targets

| **Dimension**                   | **Target**                                               |
| ------------------------------- | -------------------------------------------------------- |
| Conversational / query response | < 3 seconds                                             |
| Dashboard load                  | < 5 seconds                                             |
| Uptime                          | 99.9%                                                    |
| Scale                           | 10M+ spend transactions · 1M+ invoices · 500K+ contracts |
| Match latency (incremental)     | seconds from landing to matched                          |

## 13.3 Scaling levers

- Partition spend by tenant and period; columnar storage for history.

- Async agent queues with back-pressure; cache model calls and match results.

- Cold/warm tiering for historical spend; per-tenant quotas and circuit breakers.

- Stateless app services with horizontal autoscaling.

# 14. Operational Considerations (DevOps / MLOps / AgentOps)

## 14.1 Environments & delivery

Standard dev / staging / production environments; infrastructure-as-code; CI/CD with automated tests and schema-migration discipline; blue-green or canary releases for the app and agent runtime.

## 14.2 Observability & AgentOps

- Application: metrics, tracing, structured logs, error budgets.

- Data: freshness, volume, schema-drift and match-coverage monitors.

- Agents: per-agent traces, success/failure rates, confidence distributions, cost per run, and offline evals on golden datasets.

- Cost: model-spend dashboards and per-tenant cost attribution.

## 14.3 Reliability & incident management

Defined SLAs/SLOs; on-call and runbooks; graceful degradation (the app remains usable for analysis if an agent or model provider is unavailable); rollback paths for both code and agent actions via the audit log.

> **◉ AGENT HOOK — Data Steward (operational)**
>
> The Data Steward agent continuously reconciles totals, monitors match coverage and confidence, and proposes fixes for normalization or mapping gaps — escalating to humans when corrections would change reported figures.
>
> *Autonomy: L1 Human-in-the-loop: Approve fixes that affect numbers*

## 14.4 Quality & evaluation cadence

Regression evals run on every model/prompt change: extraction accuracy, match precision/recall, answer faithfulness, and detection rule correctness. A human review queue handles low-confidence matches and extracted terms.

# 15. Roadmap

A phased path from the validated first-party detection engine to a fully agentic control platform.

| **Horizon** | **Theme**                  | **Scope**                                                                                                             |
| ----------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Now (v1)    | First-party detection      | Spend↔contract matching; rank-1–4 opportunities; dashboard, recovery, renewals, data quality; NirvanaI ask + drafting |
| Next (v1.5) | Line-item & recovery depth | Above-rate & volume-tier (invoice line items); richer recovery packs; deeper indexation                               |
| Next (v2)   | Agentic automation         | Full agent layer in production; workflow automation; anomaly models; continuous learning loop                         |
| Later (v3)  | Control & portfolio        | Commitment Control Layer at scale; multi-entity portfolio governance; optional external-intelligence integrations     |

## 15.1 Agent rollout sequence

22. Deterministic agents first: Ingestion, Matching, Detection (high trust, code-heavy).

23. Generative assist next: Contract Extraction, Recommendation, Document/Assistant (human-reviewed).

24. Automation last: Workflow and Commitment Control behind approvals, expanded as evals prove reliability.

## 15.2 Future phases

| **Phase**                    | **Scope**                                                                                                 |
| ---------------------------- | --------------------------------------------------------------------------------------------------------- |
| Phase 2 — Integrations       | Oracle, SAP, Coupa and Workday connectors (beyond spreadsheet ingestion)                                  |
| Phase 3 — Autonomous agents  | Autonomous Procurement Agent · Cost Optimization Agent · Contract Negotiation Agent · Supplier Risk Agent |
| Phase 4 — NirvanaI ecosystem | Multi-agent NirvanaI ecosystem · predictive cost intelligence · prescriptive procurement intelligence     |

# 16. Risks & Mitigations

| **Risk**                     | **Impact**                    | **Mitigation**                                                                        |
| ---------------------------- | ----------------------------- | ------------------------------------------------------------------------------------- |
| Match inaccuracy             | Wrong figures erode trust     | Confidence on every record; unmatched surfaced; human review of low-confidence; evals |
| Sparse line-item data        | Limits above-rate/volume-tier | Phase those rules (v1.5); rely on header-level rules in v1                            |
| Agent over-automation        | Unintended external actions   | Autonomy levels; human-gated external actions; full audit & rollback                  |
| Model errors / hallucination | Bad drafts or answers         | Determinism for money; groundedness checks; human sends all drafts                    |
| External-data temptation     | Scope creep, lost wedge       | Hard first-party boundary; external intel as explicit, separate integration           |
| Data security / privacy      | Breach, compliance failure    | Tenant isolation, encryption, RBAC, AI governance, certifications                     |
| Integration variance         | Slow onboarding               | Connector framework + data contracts; agent-enforced validation                       |

# 17. Appendices

## Appendix A — Detection rule specifications (summary)

| **Rule**            | **Formula (transparent)**                                      |
| ------------------- | -------------------------------------------------------------- |
| Maverick spend      | Σ unmatched spend; savings = exposure × recapture rate (param) |
| Unused commitment   | yearly_commit − actual matched spend                          |
| Overspend vs ACV    | actual matched spend − ACV                                     |
| Silent auto-renewal | ACV × uplift% (negotiable); next-term value = ACV × (1+uplift) |
| Uplift creep        | ACV × uplift%                                                  |
| Spend after expiry  | Σ spend where spend_date > end_date                         |
| Duplicate invoice   | invoice amount × (occurrences − 1)                             |

## Appendix B — Agent placeholder index

AGENT HOOK callouts appear throughout this document at each integration surface: data ingestion (§7.3, §10.3), intelligence generation (§2.3, §11.3), anomaly detection (§8.2), recommendations (§8.6), workflow automation (§5.4), user assistance (§4, §12.3), and operational data stewardship (§14.3). Each marks where an agent acts, its autonomy level, and its human-in-the-loop requirement. Detailed prompts, tool definitions and evals for each agent are to be authored during implementation.

## Appendix C — Glossary

| **Term**             | **Definition**                                     |
| -------------------- | -------------------------------------------------- |
| ACV / TCV            | Annual / total contract value                      |
| Maverick spend       | Spend with no governing contract                   |
| SUM                  | Spend under management (% on active contract)      |
| Match confidence     | Certainty of a spend↔contract link (PO vs. fuzzy)  |
| Recovery vs. savings | Past recoverable cash vs. recurring future savings |
| Indexed exposure     | Cost risk from index/COLA-linked contract terms    |
| HITL                 | Human-in-the-loop                                  |
| AgentRun             | Immutable audit record of an agent or human action |

## Appendix D — Figure index

Figures appear inline at the relevant sections: conceptual architecture (§3.3), agent layer (§5.2), agent memory (§5.8), ingestion pipeline (§6.5), data model (§7.1), relationship matching scenarios (§8.2), opportunity lifecycle (§8.3), security trust zones (§12), and deployment & scalability (§13).
