# Terzo Cost Intelligence — Phase-wise Architecture Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Terzo Cost Intelligence platform — an AI-agent-driven SaaS that maps enterprise spend to contracts, surfaces leakage/savings opportunities, and provides conversational intelligence via NirvanaI.

**Architecture:** An event-driven, multi-tenant SaaS with a Next.js frontend, FastAPI backend, PostgreSQL + pgvector canonical store, Redis-backed agent task queue, and a LangGraph-orchestrated agent layer. Agents run in the ingest-once/operate-from-memory model — initial sync builds relationships and intelligence into a cached memory layer; subsequent queries are served from that cache without re-hitting source systems.

**Tech Stack:** Next.js 14 (App Router) · TypeScript · Tailwind CSS · shadcn/ui · FastAPI (Python 3.12+) · PostgreSQL 16 + pgvector · ClickHouse (analytics) · Redis (queues + event streams) · Celery (agent workers) · LangGraph (agent orchestration) · Claude claude-sonnet-4-6 / claude-haiku-4-5 (LLM) · Auth0 (SSO/SAML/SCIM) · Docker · GitHub Actions

---

## Architecture Principles (applies to all phases)

| Principle | Implementation |
|-----------|----------------|
| Ingest-once, operate-from-memory | Initial sync → memory store; Refresh is explicit user action |
| Determinism for money | All $ math in Python code, never in LLM calls |
| First-party data only | No external benchmarks in v1; out-of-scope endpoints labeled "requires external data" |
| Confidence on everything | Every MatchResult, Opportunity, AgentRun carries a confidence score |
| Immutable audit trail | AgentRun / AuditEvent records are append-only; no deletes |
| Human-in-the-loop gating | No irreversible external action without explicit human approval |
| Tenant isolation | Row-level security on all tables; per-tenant encryption keys |

---

## Recommended Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui | Full-stack React, server components for data-heavy views, shadcn for Terzo Design System alignment |
| Backend API | FastAPI (Python 3.12+), Pydantic v2 | Async-native, best AI/ML ecosystem, strong typing |
| Task / Agent workers | Celery + Redis | Async agent execution with back-pressure, retries, visibility |
| Event bus | Redis Streams (v1), Kafka (v2+) | Decouples ingestion → matching → detection; upgrade path at scale |
| Canonical store | PostgreSQL 16 | Multi-tenant OLTP, row-level security, ACID |
| Vector / memory store | pgvector (PostgreSQL extension) | Contract embeddings co-located with canonical data; upgrade to Pinecone at scale |
| Analytics / warehouse | ClickHouse | Columnar, fast aggregations on 10M+ spend rows |
| Object store | AWS S3 / GCS | Contract documents, CSV exports, agent artifacts |
| Auth | Auth0 | SSO/SAML/SCIM, RBAC, MFA — enterprise-ready |
| LLM (complex) | Claude claude-sonnet-4-6 | Extraction, drafting, conversation (highest capability) |
| LLM (routing/classification) | claude-haiku-4-5 | Taxonomy classification, routing, cost-sensitive tasks |
| Agent orchestration | LangGraph | Stateful, multi-step agent graphs; checkpointing; human-in-the-loop nodes |
| Model gateway | Custom FastAPI middleware | Provider routing, version pinning, PII redaction, cost tracking |
| Infra / IaC | Docker + Terraform + GitHub Actions | Reproducible environments, CI/CD |
| Observability | OpenTelemetry + Grafana / Datadog | App metrics, agent traces, model cost dashboards |

---

## Monorepo Structure

```
cost-intelligence/
├── apps/
│   ├── web/                         # Next.js 14 frontend
│   │   ├── app/                     # App Router pages & layouts
│   │   │   ├── (auth)/              # Login, SSO callback
│   │   │   ├── (dashboard)/         # Protected app routes
│   │   │   │   ├── dashboard/
│   │   │   │   ├── spend-explorer/
│   │   │   │   ├── contracts/
│   │   │   │   ├── vendors/
│   │   │   │   ├── renewals/
│   │   │   │   ├── margin-recovery/
│   │   │   │   ├── opportunity-assessment/
│   │   │   │   ├── indexation/
│   │   │   │   ├── commitment-check/
│   │   │   │   ├── portfolio/
│   │   │   │   ├── data-quality/
│   │   │   │   └── nirvanaI/
│   │   ├── components/
│   │   │   ├── ui/                  # shadcn/ui base components
│   │   │   ├── modules/             # Per-module feature components
│   │   │   └── nirvana/             # NirvanaI chat components
│   │   └── lib/                     # API client, hooks, utils
│   └── api/                         # FastAPI backend
│       ├── app/
│       │   ├── api/                 # Route handlers (v1/)
│       │   ├── agents/              # Agent definitions (LangGraph)
│       │   │   ├── ingestion.py
│       │   │   ├── enrichment.py
│       │   │   ├── matching.py
│       │   │   ├── extraction.py
│       │   │   ├── detection.py
│       │   │   ├── anomaly.py
│       │   │   ├── recommendation.py
│       │   │   ├── document_action.py
│       │   │   ├── workflow_automation.py
│       │   │   ├── commitment_control.py
│       │   │   ├── assistant.py
│       │   │   ├── data_steward.py
│       │   │   └── orchestrator.py
│       │   ├── connectors/          # Source connectors
│       │   │   ├── base.py
│       │   │   ├── google_sheets.py
│       │   │   ├── csv_excel.py
│       │   │   └── erp/             # Phase 9+
│       │   ├── models/              # SQLAlchemy ORM models
│       │   ├── schemas/             # Pydantic schemas (API + data contracts)
│       │   ├── services/            # Business logic
│       │   │   ├── matching.py      # Deterministic matching engine
│       │   │   ├── detection.py     # Rule engine
│       │   │   ├── memory.py        # Memory layer service
│       │   │   └── model_gateway.py # LLM routing + PII redaction
│       │   ├── workers/             # Celery task definitions
│       │   └── core/                # Config, auth, DB, multi-tenancy
├── packages/
│   ├── shared-types/                # Shared TypeScript types (web ↔ API contracts)
│   └── detection-rules/             # Rule specs (shared between services)
├── infra/                           # Terraform, Docker Compose, K8s manifests
├── migrations/                      # Alembic database migrations
├── evals/                           # Golden datasets, eval harnesses
└── docs/
    └── superpowers/plans/
```

---

## Phase 0: Foundation & Infrastructure

**Delivers:** A running monorepo skeleton with auth, multi-tenant database, and CI — the "empty shell" every phase builds on.

**Duration estimate:** 1–2 weeks

### Architecture decisions locked in this phase
- Monorepo structure (apps/web + apps/api + packages/)
- PostgreSQL as canonical store with row-level security for multi-tenancy
- Auth0 for SSO/SAML (tenant isolation at identity layer)
- FastAPI + Pydantic v2 as the API contract standard
- Next.js App Router + shadcn/ui aligned to Terzo Design System

### Files created
| File | Purpose |
|------|---------|
| `apps/api/app/core/config.py` | Environment config (DB URL, Redis, Auth0, LLM keys) |
| `apps/api/app/core/database.py` | SQLAlchemy async engine, session factory |
| `apps/api/app/core/tenancy.py` | Tenant context middleware; row-level security injection |
| `apps/api/app/core/auth.py` | Auth0 JWT validation; user/tenant resolution |
| `apps/api/app/models/base.py` | Base ORM model with `tenant_id`, `created_at`, `updated_at` |
| `apps/api/app/models/tenant.py` | Tenant, Entity (legal BU), User, Role |
| `apps/api/app/models/audit.py` | AgentRun / AuditEvent (append-only) |
| `migrations/001_initial_schema.py` | Alembic migration: tenants, entities, users, audit log |
| `apps/web/app/layout.tsx` | Root layout with Auth0 provider |
| `apps/web/app/(auth)/login/page.tsx` | SSO login page |
| `infra/docker-compose.yml` | PostgreSQL, Redis, ClickHouse, API, Web |
| `.github/workflows/ci.yml` | Lint, type-check, test, migrate on PR |

### Key tasks
- [ ] Scaffold monorepo (`pnpm` workspaces + `uv` for Python)
- [ ] Bootstrap FastAPI app with Auth0 JWT middleware and tenant context
- [ ] Bootstrap Next.js app with Auth0 session handling
- [ ] Create PostgreSQL schema: `tenants`, `entities`, `users`, `roles`, `agent_runs`, `audit_events`
- [ ] Enable pgvector extension; add `embeddings` table skeleton
- [ ] Implement row-level security policy: `tenant_id = current_setting('app.tenant_id')`
- [ ] Set up Alembic migration workflow
- [ ] Configure Docker Compose (postgres + pgvector + redis + clickhouse + api + web)
- [ ] Set up GitHub Actions CI (lint, typecheck, pytest, migration dry-run)

---

## Phase 1: Data Ingestion & Google Sheets Connector

**Delivers:** Ability to ingest Contracts, Invoices and Spend Transactions from Google Sheets into the canonical PostgreSQL store via a validated, event-emitting Ingestion agent.

**Duration estimate:** 2–3 weeks

### Architecture: Connector Framework

```
Google Sheets → ConnectorBase → IngestionAgent → Validated Records → Redis Stream (records.landed) → [downstream agents]
```

Every connector declares a **data contract** (expected fields, types, freshness, volume). The Ingestion agent validates each batch, quarantines failing records, deduplicates, and emits `records.landed` events. Schema drift → `data_quality.schema_drift` event, not silent corruption.

### Files created
| File | Purpose |
|------|---------|
| `apps/api/app/connectors/base.py` | `ConnectorBase` ABC: auth, fetch, validate, emit |
| `apps/api/app/connectors/google_sheets.py` | Google Sheets connector (OAuth2, sheet-to-DataFrame) |
| `apps/api/app/schemas/data_contracts.py` | Pydantic schemas for Contract, SpendRecord, Invoice (inbound) |
| `apps/api/app/models/vendor.py` | `Vendor` (canonical), `VendorAlias` |
| `apps/api/app/models/contract.py` | `Contract`, `ContractLineItem`, `ContractClause` |
| `apps/api/app/models/spend.py` | `SpendRecord` |
| `apps/api/app/models/invoice.py` | `Invoice`, `InvoiceLineItem` |
| `apps/api/app/models/staging.py` | `StagedRecord` (quarantine buffer) |
| `apps/api/app/agents/ingestion.py` | LangGraph ingestion agent (L2, deterministic) |
| `apps/api/app/services/vendor_normalization.py` | Canonical vendor_id via fuzzy name dedup |
| `apps/api/app/workers/ingestion_tasks.py` | Celery tasks: run_ingestion, refresh_source |
| `apps/api/app/api/v1/data_sources.py` | REST: list/add/delete data sources; trigger refresh |
| `apps/web/app/(dashboard)/settings/data-sources/page.tsx` | Data Sources settings UI |
| `migrations/002_core_entities.py` | vendors, contracts, spend_records, invoices, staged_records |

### Data contracts (Pydantic schemas)

```python
# schemas/data_contracts.py
class InboundContract(BaseModel):
    vendor_name: str
    acv: Decimal
    tcv: Decimal
    start_date: date
    end_date: date
    renewal_type: Literal["auto", "option", "none"]
    renewal_notice_days: int
    uplift_pct: Optional[Decimal]
    yearly_commit: Optional[Decimal]
    po_number: Optional[str]
    # ...95+ fields per blueprint

class InboundSpendRecord(BaseModel):
    vendor_name: str
    amount: Decimal
    currency: str = "USD"
    spend_date: date
    gl_code: Optional[str]
    cost_center: Optional[str]
    po_number: Optional[str]
    source_system: Literal["coupa", "oracle", "sap", "manual", "sheets"]
```

### Vendor normalization strategy
1. Lowercase + strip punctuation → fingerprint
2. Fuzzy match existing canonical vendors (threshold: 0.85 Jaro-Winkler)
3. New fingerprint → new canonical vendor; alias stored in `VendorAlias`
4. `canonical_vendor_id` used as matching fallback when PO is missing

### Agent: Ingestion (L2)
- **Trigger:** File drop / Google Sheets webhook / scheduled pull / manual Refresh
- **Inputs:** Raw sheet data + data contract spec
- **Outputs:** Validated canonical records in PostgreSQL + `records.landed` Redis stream event
- **On failure:** Quarantine to `StagedRecord.status = 'quarantine'`; emit `data_quality.schema_drift`
- **Autonomy:** L2 — acts, logs, reversible (no records deleted from source)
- **HITL:** Review quarantine queue on contract violations

### Key tasks
- [ ] Implement `ConnectorBase` with `fetch()`, `validate()`, `emit()` interface
- [ ] Implement `GoogleSheetsConnector` (OAuth2 via Google API client; read named ranges)
- [ ] Create Pydantic data contracts for all three inbound datasets
- [ ] Implement vendor normalization service (fuzzy dedup → canonical_vendor_id)
- [ ] Build Ingestion agent (LangGraph graph: validate → normalize → dedupe → stage → emit)
- [ ] Create `data_sources` API endpoints (add/list/refresh/delete)
- [ ] Create Celery tasks for async ingestion execution
- [ ] Build Data Sources settings UI page (list connected sources, last sync, status)
- [ ] Write integration tests against a fixture Google Sheet

---

## Phase 2: Spend↔Contract Matching Engine

**Delivers:** Every spend record is linked to its governing contract (or flagged as unmatched/maverick) with a confidence score and full lineage. The MatchResult table is the evidentiary backbone for all downstream opportunity detection.

**Duration estimate:** 2 weeks

### Matching pipeline

```
SpendRecord → [1] PO match → [2] Fuzzy fallback → [3] Unmatched bucket
                                                        ↓
                                                 MatchResult + confidence
```

1. **PO match** (deterministic, confidence = 1.0): `spend.po_number == contract.po_number`
2. **Fuzzy fallback** (confidence = 0.5–0.95): normalized vendor_id + cost_center + amount/date similarity
3. **Unmatched** (confidence = 0.0): surfaced as maverick exposure — never hidden

### Files created
| File | Purpose |
|------|---------|
| `apps/api/app/models/matching.py` | `MatchResult` (match_id, spend_id, contract_id, method, confidence, discrepancies) |
| `apps/api/app/services/matching.py` | `MatchingService`: deterministic + fuzzy + confidence scoring |
| `apps/api/app/agents/matching.py` | Matching agent (triggers on `records.landed`; writes MatchResults) |
| `apps/api/app/workers/matching_tasks.py` | Celery: `run_matching_for_spend`, `rematch_contract` |
| `apps/api/app/api/v1/matching.py` | REST: get match results; trigger rematch; review low-confidence |
| `migrations/003_match_results.py` | `match_results` table |
| `evals/matching/golden_dataset.csv` | 100+ labeled spend-to-contract pairs for regression evals |
| `evals/matching/eval_harness.py` | Precision/recall measurement against golden dataset |

### MatchResult model

```python
class MatchResult(Base):
    match_id: UUID (PK)
    tenant_id: UUID (FK, RLS)
    spend_id: UUID (FK → SpendRecord)
    contract_id: Optional[UUID] (FK → Contract)  # None = unmatched
    invoice_id: Optional[UUID] (FK → Invoice)
    method: Literal["po_exact", "po_fuzzy", "vendor_amount_date", "ai_inferred", "unmatched"]
    confidence: Decimal  # 0.0–1.0
    discrepancies: JSONB  # {field: {expected, actual}} for overspend / rate diff
    matched_by: Literal["system", "human"]
    created_at: datetime
```

### Matching scenario support (per §8.2 relationship intelligence)
- **Scenario 1**: Contract + Invoice + Spend all present → full chain link
- **Scenario 2**: Invoice missing → Contract → Spend, AI-inferred (LLM assists, confidence flagged)
- **Scenario 3**: Multiple contracts/invoices/spend → confidence-based ranking across candidates; human review if tie

### Confidence thresholds
| Range | Action |
|-------|--------|
| 0.90–1.0 | Auto-match; no review required |
| 0.70–0.89 | Auto-match; flagged in Data Quality queue for spot-check |
| 0.50–0.69 | Staged match; human review required before accepted |
| < 0.50 | Unmatched; surfaced as maverick spend |

### Agent: Matching (L2)
- **Trigger:** `records.landed` stream event; also on contract update
- **Inputs:** New/changed spend or contract records
- **Outputs:** MatchResults + unmatched queue entries
- **Autonomy:** L2 — auto-matches high-confidence; queues low-confidence for human
- **HITL:** Human reviews low-confidence in Data Quality module

### Key tasks
- [ ] Implement `MatchingService.match_by_po()` (exact string match on po_number)
- [ ] Implement `MatchingService.match_fuzzy()` (vendor_id + cost_center + amount window + date window → score)
- [ ] Implement confidence scoring formula and thresholds
- [ ] Create MatchResult ORM model with JSONB discrepancies field
- [ ] Build Matching agent (LangGraph: PO match → fuzzy fallback → AI inference → emit `matches.completed`)
- [ ] Subscribe Celery worker to `records.landed` stream
- [ ] Write eval harness against golden dataset; target > 90% precision, > 85% recall
- [ ] API endpoint: list match results, filter by confidence, trigger rematch

---

## Phase 3: Detection Rule Engine (v1 Opportunities)

**Delivers:** The platform detects and quantifies all v1 leakage/savings types — maverick spend, unused commitment, overspend vs ACV, silent auto-renewal, uplift creep, spend after expiry, and duplicate invoices. Each finding becomes a tracked, dollar-quantified Opportunity.

**Duration estimate:** 2 weeks

### Detection rule catalog (v1)

| Rule | Formula | Bucket |
|------|---------|--------|
| Maverick / off-contract | `Σ unmatched spend × recapture_rate` | Savings |
| Unused commitment | `yearly_commit − Σ matched spend` (when delta > threshold) | Savings |
| Overspend vs ACV | `Σ matched spend − ACV` (when positive) | Recovery |
| Silent auto-renewal | `ACV × (1 + uplift_pct)` for contracts inside notice window | Savings |
| Uplift creep | `ACV × uplift_pct` (any uplift > 0) | Savings |
| Spend after expiry | `Σ spend where spend_date > contract.end_date` | Recovery |
| Duplicate invoice | `invoice_amount × (occurrences − 1)` | Recovery |
| Missing invoice | Spend / PO with no matching Invoice | Control |

**All formulas are executed in Python code, never in an LLM.**

### Files created
| File | Purpose |
|------|---------|
| `apps/api/app/models/opportunity.py` | `Opportunity`, `RecoveryItem` |
| `apps/api/app/services/detection.py` | `DetectionService`: runs all rules; returns Opportunity list |
| `apps/api/app/services/rules/` | One file per rule: `maverick.py`, `unused_commitment.py`, `overspend.py`, `auto_renewal.py`, `uplift_creep.py`, `post_expiry.py`, `duplicate_invoice.py`, `missing_invoice.py` |
| `apps/api/app/services/scoring.py` | `impact × confidence` ranking; effort + time-sensitivity secondary sort |
| `apps/api/app/agents/detection.py` | Detection agent (wraps rule engine; L2) |
| `apps/api/app/agents/recommendation.py` | Recommendation agent (ranks + writes rationale via LLM; L1) |
| `apps/api/app/workers/detection_tasks.py` | Celery: `run_detection_for_tenant`, `recompute_opportunity` |
| `apps/api/app/api/v1/opportunities.py` | REST: list/get/update opportunity status |
| `migrations/004_opportunities.py` | `opportunities`, `recovery_items` tables |
| `evals/detection/golden_opportunities.json` | Expected opportunities on the synthetic dataset |
| `evals/detection/eval_harness.py` | Opportunity precision/recall vs golden set |

### Opportunity model

```python
class Opportunity(Base):
    opp_id: UUID (PK)
    tenant_id: UUID (FK, RLS)
    contract_id: UUID (FK → Contract)
    type: Literal["maverick", "unused_commitment", "overspend", "auto_renewal",
                  "uplift_creep", "post_expiry", "duplicate_invoice", "missing_invoice"]
    bucket: Literal["savings", "recovery", "control"]
    impact: Decimal          # $ impact (code-computed, not LLM)
    confidence: Decimal      # inherited from underlying MatchResult confidence
    status: Literal["detected", "triaged", "in_progress", "realized", "dismissed"]
    owner_id: Optional[UUID]
    rationale: Optional[str]  # LLM-generated rationale (Recommendation agent)
    evidence: JSONB           # spend_ids, invoice_ids, formula used
    created_at: datetime
    updated_at: datetime
```

### Agent: Detection (L2)
- **Trigger:** `matches.completed` event; also on schedule (daily)
- **Inputs:** Reconciled MatchResults + Contract + SpendRecord data
- **Outputs:** Opportunity records (upsert by type+contract; don't duplicate)
- **Autonomy:** L2 — fully automated, no human needed for read-only analysis
- **HITL:** None — detection is observational

### Agent: Recommendation (L1)
- **Trigger:** New/updated Opportunity
- **Inputs:** Opportunity + contract + spend context
- **Outputs:** Ranked next actions with rationale (LLM-generated, citation-grounded)
- **Autonomy:** L1 — advisory only
- **HITL:** No — advice is visible to user but requires no approval

### Key tasks
- [ ] Implement each rule as a standalone Python function with unit tests
- [ ] Implement `DetectionService.run_all_rules(tenant_id)` → list of `Opportunity`
- [ ] Build deduplication: upsert opportunities by (type, contract_id) — don't create duplicates on re-run
- [ ] Build `ScoringService.rank(opportunities)` → sorted list by `impact × confidence`
- [ ] Build Recommendation agent (LangGraph: fetch context → prompt claude-sonnet-4-6 → write rationale with citations)
- [ ] Wire Celery task to `matches.completed` stream
- [ ] API endpoints: `GET /opportunities`, `PATCH /opportunities/{id}/status`
- [ ] Run on synthetic dataset: verify ~$241K opportunity total and 94.9% match coverage from blueprint prototype

---

## Phase 4: Agent Memory Layer & Ingest-Once Architecture

**Delivers:** The platform's ingest-once/operate-from-memory model. After an initial sync, the agent reads each source once, builds relationships, generates intelligence, and stores everything in a memory layer. Queries are served from memory — not re-hitting source systems.

**Duration estimate:** 1–2 weeks**

### Memory architecture

```
Initial Sync:
  Source → Ingestion → Matching → Detection → [intelligence] → Memory Store
                                                                    ↓
Operational Mode:                                           MemoryService.query()
  User query → MemoryService → answer (< 3s)

Refresh:
  Settings → "Refresh Data" → re-run full sync → update memory
```

**Memory store components:**
1. **Structured intelligence cache** — PostgreSQL: pre-computed KPIs, opportunity summaries, contract summaries per tenant
2. **Vector store (pgvector)** — contract text, clauses, prior NirvanaI interactions → embeddings for RAG
3. **Redis cache** — dashboard KPIs, opportunity counts (sub-second reads)

### Files created
| File | Purpose |
|------|---------|
| `apps/api/app/services/memory.py` | `MemoryService`: build(), query(), refresh(), get_kpis() |
| `apps/api/app/models/memory.py` | `TenantMemory` (structured intelligence snapshot), `ContractEmbedding` |
| `apps/api/app/services/embeddings.py` | Embed contracts/clauses via Claude Embeddings; store in pgvector |
| `apps/api/app/workers/sync_tasks.py` | Celery: `initial_sync`, `refresh_sync` (orchestrate all agent stages) |
| `apps/api/app/api/v1/sync.py` | REST: `POST /sync/initial`, `POST /sync/refresh`, `GET /sync/status` |
| `apps/api/app/models/agent_run.py` | Full `AgentRun` / `AuditEvent` ORM (immutable, append-only) |
| `migrations/005_memory_layer.py` | `tenant_memory`, `contract_embeddings`, `agent_runs` |

### TenantMemory snapshot (stored per tenant)

```python
class TenantMemory(Base):
    tenant_id: UUID (PK)
    last_synced_at: datetime
    total_spend: Decimal
    spend_under_management_pct: Decimal
    contract_compliance_pct: Decimal
    total_opportunity_savings: Decimal
    total_opportunity_recovery: Decimal
    opportunity_count_by_type: JSONB
    top_opportunities: JSONB  # top 10 ranked
    vendor_summary: JSONB
    renewal_calendar: JSONB   # contracts expiring in next 90/180/365 days
    kpi_snapshot: JSONB       # all dashboard KPIs
    stale: bool               # true when source data changed but refresh not run
```

### Sync orchestration (Celery chain)

```python
# workers/sync_tasks.py
@celery.task
def initial_sync(tenant_id: str, source_id: str):
    chain(
        run_ingestion.s(tenant_id, source_id),
        run_enrichment.s(tenant_id),
        run_matching.s(tenant_id),
        run_detection.s(tenant_id),
        build_memory.s(tenant_id),
        embed_contracts.s(tenant_id),
    ).apply_async()
```

### AgentRun / AuditEvent (immutable)

```python
class AgentRun(Base):
    run_id: UUID (PK)
    tenant_id: UUID (FK, RLS)
    agent: str              # "ingestion", "matching", "detection", etc.
    trigger: str            # "initial_sync", "refresh", "user_request"
    inputs_ref: str         # S3/storage reference to input snapshot
    outputs_ref: str        # S3 reference to output snapshot
    confidence: Optional[Decimal]
    actor: Literal["ai", "human"]
    status: Literal["running", "completed", "failed"]
    error: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    # No updates, no deletes — append only
```

### Key tasks
- [ ] Implement `MemoryService.build(tenant_id)` — runs after full sync; writes TenantMemory snapshot
- [ ] Implement `MemoryService.get_kpis(tenant_id)` → reads from Redis cache (fallback: PostgreSQL)
- [ ] Implement `EmbeddingsService` — embed contract text + clauses via `text-embedding-3-small`; store in pgvector
- [ ] Implement `initial_sync` and `refresh_sync` Celery chains
- [ ] Implement full `AgentRun` logging in all existing agents
- [ ] Build `GET /sync/status` API — returns last sync timestamp, stale flag, coverage stats
- [ ] Add "Refresh Data" button to Data Sources settings UI → calls `POST /sync/refresh`
- [ ] Confirm < 3s query response from memory (benchmark test)

---

## Phase 5: Core Application Modules (v1 UI)

**Delivers:** The full v1 UI — Dashboard, Spend Explorer, Contracts, Renewals, Margin Recovery, Data Quality, and Opportunity Assessment — all served from the memory layer with < 5s load time.

**Duration estimate:** 4–5 weeks (can parallelize module development)

### Design system requirement
All UI must follow the Terzo Design System and the approved Terzo Cost Intelligence prototype. shadcn/ui components are the base; tokens/colors/typography are overridden to match Terzo's design language. No deviations without product approval (per §9.1).

### Module breakdown

#### 5.1 Dashboard
**Purpose:** At-a-glance health — KPI tiles, alerts, opportunity-by-type chart.

| Component | Source |
|-----------|--------|
| KPI tiles: Spend Under Management, Contract Compliance %, PO Coverage %, Identified Savings, Recoverable Cash | `MemoryService.get_kpis()` |
| Opportunity-by-type chart (savings vs recovery, by rule type) | `MemoryService.opportunity_count_by_type` |
| Active alerts (auto-renewals in window, post-expiry spend) | `OpportunityService.get_alerts()` |
| NirvanaI chat panel (persistent across all modules) | Phase 6 |

Files: `apps/web/app/(dashboard)/dashboard/page.tsx`, `components/modules/dashboard/`

#### 5.2 Opportunity Assessment
**Purpose:** EBITDA-style ranked list of opportunities; 4-week sprint plan.

| Component | Source |
|-----------|--------|
| Ranked opportunity list (impact × confidence sort) | `GET /opportunities?sort=ranked` |
| Impact / confidence badges | Opportunity model |
| Bucket filter (savings / recovery / control) | Client-side filter |
| Assign owner + change status | `PATCH /opportunities/{id}` |
| 4-week sprint plan (top-N grouped by week by effort) | `RecommendationAgent` output |

Files: `apps/web/app/(dashboard)/opportunity-assessment/page.tsx`, `components/modules/opportunity/`

#### 5.3 Spend Explorer
**Purpose:** Categorized spend with L1/L2 taxonomy, vendor/category/cost-center filters, trend charts.

| Component | Source |
|-----------|--------|
| Spend by vendor (table + bar chart) | `GET /spend/by-vendor` |
| Spend by category (L1/L2 taxonomy tree) | `GET /spend/by-category` |
| Spend by cost center | `GET /spend/by-cost-center` |
| Time trend (monthly) | `GET /spend/trend?period=12m` |
| Matched vs unmatched split | `GET /spend/match-coverage` |

Files: `apps/web/app/(dashboard)/spend-explorer/page.tsx`, `apps/api/app/api/v1/spend.py`

#### 5.4 Contracts
**Purpose:** Contract register with terms, utilization bars, indexation, linked spend.

| Component | Source |
|-----------|--------|
| Contract list (vendor, ACV/TCV, status, renewal date) | `GET /contracts` |
| Contract detail (all 95+ fields, linked spend, utilization bar) | `GET /contracts/{id}` |
| Utilization bar: actual spend vs yearly_commit / ACV | Computed from MatchResults |
| Linked spend transactions | `GET /contracts/{id}/spend` |
| Indexation / COLA terms badge | Contract.index_type |

Files: `apps/web/app/(dashboard)/contracts/`, `apps/api/app/api/v1/contracts.py`

#### 5.5 Renewals
**Purpose:** Renewal calendar sorted by urgency; uplift exposure per contract.

| Component | Source |
|-----------|--------|
| Renewals calendar (sorted by `end_date − notice_days`) | `GET /renewals?window=90` |
| Urgency badge (red: < 30 days, amber: 30–60 days, green: 60+) | Computed |
| Auto-renewal warning flag | `renewal_type == "auto"` |
| Uplift exposure: `ACV × uplift_pct` | Computed |
| Generate renegotiation / non-renewal notice | Phase 6 (NirvanaI) |

Files: `apps/web/app/(dashboard)/renewals/`, `apps/api/app/api/v1/renewals.py`

#### 5.6 Margin Recovery
**Purpose:** Recovery packs for supplier challenge; challenge letter generation; status workflow.

| Component | Source |
|-----------|--------|
| Recovery packs grouped by vendor | `GET /recovery/packs` |
| Pack detail: evidence (spend lines, formula), total recoverable | RecoveryItem model |
| Status workflow: detected → in-progress → recovered | `PATCH /recovery/{id}/status` |
| Generate challenge letter | Phase 6 (NirvanaI Document agent) |
| Root-cause prevention control suggestion | Phase 7 (Data Steward agent) |

Files: `apps/web/app/(dashboard)/margin-recovery/`, `apps/api/app/api/v1/recovery.py`

#### 5.7 Data Quality
**Purpose:** Match confidence visibility; unmatched queue; fuzzy-match review.

| Component | Source |
|-----------|--------|
| Match coverage % (matched vs total spend) | `GET /data-quality/coverage` |
| Low-confidence match queue (< 0.70) | `GET /match-results?confidence_lt=0.70` |
| Unmatched spend queue | `GET /match-results?method=unmatched` |
| Human review: accept / re-assign match | `PATCH /match-results/{id}` |
| Schema drift log | `GET /data-quality/events` |

Files: `apps/web/app/(dashboard)/data-quality/`, `apps/api/app/api/v1/data_quality.py`

### Key tasks (Phase 5)
- [ ] Create shared layout: sidebar nav, NirvanaI chat panel placeholder, tenant switcher
- [ ] Implement all API endpoints for Dashboard, Spend Explorer, Contracts, Renewals, Margin Recovery, Data Quality
- [ ] Build each module page + key components (table, chart, detail panel)
- [ ] Connect all read paths to memory layer / PostgreSQL (no direct source re-query)
- [ ] Implement Opportunity status workflow (detected → triaged → in_progress → realized/dismissed)
- [ ] Add < 5s dashboard load performance test (memory layer benchmark)
- [ ] Test with synthetic dataset matching blueprint prototype ($1.69M spend, 10 contracts, ~$241K opportunity)

---

## Phase 6: NirvanaI Assistant

**Delivers:** Conversational Q&A grounded in first-party data, available on every module; document generation (challenge letters, non-renewal notices, RFP briefs, supplier SWOTs).

**Duration estimate:** 3 weeks

### NirvanaI architecture

```
User message
    ↓
AssistantAgent (LangGraph)
    ├── Intent classification (claude-haiku-4-5: Q&A vs. document generation)
    ├── [Q&A path] RAG retrieval (pgvector: contracts + clauses + memory)
    │       → claude-sonnet-4-6 → grounded answer + source citations
    └── [Document path] Template selection → context fetch → claude-sonnet-4-6
            → editable draft document (human reviews + sends)
```

**Groundedness constraint:** Every numerical answer must cite the source record (contract_id, spend_id, or opportunity_id). No fabricated figures. Checked via output validation before returning to user.

**Access control:** RAG retrieval is tenant-scoped + user RBAC-scoped (per §12.3 — user sees only data they're authorized for). RLS enforced at the PostgreSQL query layer before embedding retrieval.

### Files created
| File | Purpose |
|------|---------|
| `apps/api/app/agents/assistant.py` | NirvanaI LangGraph agent (intent → RAG/generate → validate) |
| `apps/api/app/services/rag.py` | `RAGService`: pgvector similarity search + reranking |
| `apps/api/app/services/document_templates.py` | Document template registry: challenge letter, non-renewal notice, RFP brief, supplier SWOT |
| `apps/api/app/agents/document_action.py` | Document/Action agent (context fetch → LLM draft → return editable) |
| `apps/api/app/api/v1/nirvana.py` | REST: `POST /nirvana/chat`, `POST /nirvana/generate-doc`, `GET /nirvana/history` |
| `apps/api/app/core/model_gateway.py` | LLM routing + version pinning + PII redaction + cost tracking |
| `apps/web/components/nirvana/ChatPanel.tsx` | Persistent chat panel (slide-in, available on every page) |
| `apps/web/components/nirvana/DocumentPreview.tsx` | Editable document draft with approve/edit/send UI |
| `apps/web/components/nirvana/MessageBubble.tsx` | Chat bubble with source citations (contract/spend record links) |

### Supported Q&A examples (must work out of box)
- "What auto-renews this quarter?" → pulls renewal calendar from memory
- "Where is our biggest exposure this quarter?" → top opportunities from memory
- "How much have we spent with Salesforce this year?" → spend aggregation from MatchResults
- "Which contracts have unused commitments?" → opportunities of type `unused_commitment`
- "Show me all duplicate invoices" → opportunities of type `duplicate_invoice`

### Supported document types (must work out of box)
- **Supplier challenge letter** — for Margin Recovery opportunities (overspend, post-expiry, duplicate)
- **Non-renewal notice** — for auto-renewal contracts in notice window
- **Renegotiation request** — for uplift creep / renewal opportunities
- **RFP brief** — for fragmented category (from Spend Explorer)
- **Supplier SWOT** — vendor analysis from first-party spend/contract data

### Groundedness validator

```python
# services/groundedness.py
class GroundednessValidator:
    def validate(self, answer: str, context_records: list[dict]) -> bool:
        # All $ figures in answer must appear in context_records
        # All vendor names must match canonical vendors
        # No forward-looking claims without explicit "requires external data" label
        ...
```

### Out-of-scope labeling
Queries about market benchmarks, should-cost, or "is this uplift fair vs CPI" return:
> "This question requires external market data, which is outside the scope of Terzo Cost Intelligence v1."

### Key tasks
- [ ] Implement `ModelGateway` (route to claude-sonnet-4-6 or claude-haiku-4-5; pin versions; redact PII; log cost per run)
- [ ] Implement `RAGService` (pgvector similarity search with tenant/RBAC scope; top-k retrieval + rerank)
- [ ] Build NirvanaI LangGraph agent (intent classify → route → retrieve → generate → validate → return)
- [ ] Implement `GroundednessValidator` (verify all figures cite source records)
- [ ] Build Document/Action agent for each template type
- [ ] Build `ChatPanel` React component (persistent, available on all pages)
- [ ] Build `DocumentPreview` component (editable draft, approve/send flow)
- [ ] Test all 5 Q&A examples and all 5 document types against synthetic dataset
- [ ] Verify < 3s response time for conversational queries (target from §13.2)

---

## Phase 7: Advanced Modules & Agents

**Delivers:** Vendors module (consolidation), Indexation & Exposure module, Portfolio module (multi-entity), plus the Enrichment, Contract Extraction, Anomaly, and Data Steward agents.

**Duration estimate:** 3–4 weeks

### 7.1 Vendors Module
- Canonical vendor rollup (spend by vendor, contract count, opportunity exposure)
- Consolidation candidates: vendors with > 1 contract + fragmented spend across categories
- Enrichment agent: normalize aliases, classify categories (claude-haiku-4-5)

Files: `apps/web/app/(dashboard)/vendors/`, `apps/api/app/api/v1/vendors.py`, `apps/api/app/agents/enrichment.py`

### 7.2 Indexation & Exposure Module
- Index/COLA register: contracts where `index_type` is set
- Exposure slider: model indexed cost at assumed % move (first-party assumption, not external feed)
- Detection: `indexed_exposure = ACV × indexed_share × assumed_index_move`

Files: `apps/web/app/(dashboard)/indexation/`, `apps/api/app/api/v1/indexation.py`, `apps/api/app/services/rules/indexation.py`

### 7.3 Portfolio Module
- Multi-entity rollup (CFO view across all legal entities)
- By-entity: spend, SUM %, identified opportunity, realized savings
- Only available for users with `role = "portfolio_admin"` or above

Files: `apps/web/app/(dashboard)/portfolio/`, `apps/api/app/api/v1/portfolio.py`

### 7.4 Agent: Contract Extraction (L1)
- **Trigger:** New/updated contract document uploaded to object store
- **Inputs:** Contract PDF/document (untrusted — sandboxed)
- **Outputs:** Structured contract fields (ACV, TCV, terms, COLA, rate cards) for human verification
- **Model:** claude-sonnet-4-6 (highest extraction accuracy)
- **HITL:** Human verifies extracted fields before they enter the canonical record
- **Safety:** Contract text treated as untrusted (prompt-injection defense); tool use allowlisted

Files: `apps/api/app/agents/extraction.py`, `apps/api/app/api/v1/contract_documents.py`

### 7.5 Agent: Enrichment (L2)
- **Trigger:** New staged records (post-ingestion)
- **Inputs:** Vendor names, GL codes, spend descriptions
- **Outputs:** Canonical vendor_id (refined); L1/L2 taxonomy classification; currency normalization
- **Model:** claude-haiku-4-5 (classification is cheap)
- **HITL:** Spot-check queue for low-confidence classifications

Files: `apps/api/app/agents/enrichment.py`

### 7.6 Agent: Anomaly (L1)
- **Trigger:** New spend records; weekly schedule
- **Inputs:** Spend time series per vendor/category
- **Outputs:** Anomaly flags (spike, new vendor, off-pattern GL, duplicate-payment signature)
- **Method:** Statistical (Z-score / IQR) for v1; ML model in v2
- **HITL:** Human reviews anomaly flags before they become opportunities

Files: `apps/api/app/agents/anomaly.py`, `apps/api/app/services/anomaly_detection.py`

### 7.7 Agent: Data Steward (L1)
- **Trigger:** Schedule (daily); data-quality events
- **Inputs:** MatchResult confidence distribution; schema drift events; unmatched queue
- **Outputs:** Quality metrics; fix proposals (e.g., add PO number mapping rule)
- **HITL:** Approve fixes that would change reported figures

Files: `apps/api/app/agents/data_steward.py`

### Key tasks (Phase 7)
- [ ] Build Vendors module UI and API
- [ ] Build Indexation & Exposure module UI and API
- [ ] Build Portfolio module UI and API (with RBAC gate)
- [ ] Build Contract Extraction agent (LangGraph with prompt-injection sandbox)
- [ ] Build Enrichment agent (taxonomy classification via claude-haiku-4-5)
- [ ] Build statistical anomaly detection service (Z-score per vendor/category)
- [ ] Build Anomaly agent (wraps detection; emits anomaly flags as opportunities/data-quality items)
- [ ] Build Data Steward agent (quality metrics dashboard + fix proposals)
- [ ] Expose Data Steward findings in Data Quality module

---

## Phase 8: v1.5 — Invoice Line-Item Depth & Richer Recovery

**Delivers:** Above-rate detection (invoice unit price vs contracted rate), volume-tier analysis, richer recovery packs with line-item evidence, and deeper COLA/indexation modeling.

**Duration estimate:** 3 weeks

### New capabilities
| Capability | Requires |
|-----------|---------|
| Above-rate detection | Invoice line items with unit_price + contracted rate card |
| Volume-tier analysis | Rate card tiers + actual volumes from invoice lines |
| Line-item recovery packs | `InvoiceLineItem` → `RecoveryItem` with per-line evidence |
| Deeper COLA modeling | Full COLA clause extraction (Contract Extraction agent) |

### New detection rules

```python
# services/rules/above_rate.py
def detect_above_rate(invoice: Invoice, contract: Contract) -> Optional[Opportunity]:
    """
    For each InvoiceLineItem, compare unit_price to contract rate card.
    Impact = Σ (invoice_unit_price - contracted_rate) × quantity
    Only runs where rate card is available on the contract.
    """

# services/rules/volume_tier.py
def detect_volume_tier(invoice: Invoice, contract: Contract) -> Optional[Opportunity]:
    """
    Actual volume puts buyer in a better tier than billed.
    Impact = Σ (current_tier_rate - qualified_tier_rate) × quantity
    """
```

### Files created
| File | Purpose |
|------|---------|
| `apps/api/app/models/rate_card.py` | `ContractRateCard`, `RateCardTier` |
| `apps/api/app/services/rules/above_rate.py` | Above-rate detection rule |
| `apps/api/app/services/rules/volume_tier.py` | Volume-tier detection rule |
| `apps/api/app/services/recovery_pack_builder.py` | Build line-item-level recovery packs |
| `migrations/006_rate_cards.py` | `contract_rate_cards`, `rate_card_tiers` |

### Key tasks
- [ ] Extend `InvoiceLineItem` model with `unit_price`, `quantity`, `sku`
- [ ] Create `ContractRateCard` and `RateCardTier` models
- [ ] Update Contract Extraction agent to extract rate card data
- [ ] Implement `detect_above_rate` rule
- [ ] Implement `detect_volume_tier` rule
- [ ] Update `RecoveryPackBuilder` to include line-item evidence
- [ ] Update Margin Recovery UI to show line-item breakdown in recovery packs
- [ ] Add "requires rate card data" label when rate card unavailable on contract

---

## Phase 9: v2 — Agentic Automation & ERP Connectors

**Delivers:** Workflow Automation agent (L3, human-gated); full agent orchestrator in production; ERP connectors (Coupa, SAP, Oracle); continuous learning feedback loop.

**Duration estimate:** 4–5 weeks

### 9.1 Workflow Automation Agent (L3)
- **Trigger:** High-confidence, time-sensitive opportunity (e.g., auto-renewal inside notice window)
- **Actions:** Open task, assign owner, schedule reminder, queue document draft
- **Gating:** All external actions (send letter, post Slack) require human approval
- **Autonomy:** L3 — higher-risk actions behind approval gate

```python
# agents/workflow_automation.py
class WorkflowAutomationAgent:
    """
    On: auto-renewal detected inside notice window
    Does: create Task → assign owner → draft non-renewal notice (Document agent)
    Gate: human approves before external send
    """
```

Files: `apps/api/app/agents/workflow_automation.py`, `apps/api/app/models/task.py`

### 9.2 ERP Connectors
- `apps/api/app/connectors/erp/coupa.py` — Coupa REST API connector
- `apps/api/app/connectors/erp/oracle.py` — Oracle Fusion connector
- `apps/api/app/connectors/erp/sap.py` — SAP connector
Each follows the `ConnectorBase` interface established in Phase 1.

### 9.3 Continuous Learning Loop
- Match scoring improvement: human-confirmed matches feed back as labeled examples
- Classification improvement: human-corrected taxonomy labels feed Enrichment agent fine-tuning
- Detection calibration: dismissed/confirmed opportunities adjust rule thresholds

Files: `apps/api/app/services/feedback_loop.py`, `apps/api/app/workers/learning_tasks.py`

### 9.4 Anomaly Models (ML-based)
Upgrade from statistical anomaly detection (Phase 7) to a lightweight ML model (Isolation Forest or similar) trained on tenant spend history.

Files: `apps/api/app/services/anomaly_ml.py`

### Key tasks
- [ ] Build Workflow Automation agent (LangGraph with human-in-the-loop approval nodes)
- [ ] Build `Task` model + task management API + UI (tasks assigned to users)
- [ ] Build Coupa connector (OAuth2, pull invoices + POs)
- [ ] Build Oracle connector (scheduled pull from Fusion REST)
- [ ] Build SAP connector (file-based extract or RFC interface)
- [ ] Implement feedback loop service (human labels → training examples)
- [ ] Implement ML anomaly model (train on 90-day spend history)
- [ ] Extend `/settings/data-sources` UI to support ERP connector auth flows

---

## Phase 10: v3 — Commitment Check & Multi-entity Portfolio Governance

**Delivers:** Pre-signature Commitment Check (stress test + approve/condition/block verdict), full multi-entity portfolio governance, and the integration seam for optional external intelligence.

**Duration estimate:** 3–4 weeks**

### 10.1 Commitment Check Module
- User enters proposed deal terms (vendor, ACV, index-linked share, assumed index %)
- Commitment Control agent computes: indexed exposure, ±5/10/15% stress scenarios
- Returns verdict: `approve` / `condition` / `block` against configured margin tolerance
- Verdict is advisory; human signs off

```python
# agents/commitment_control.py
class CommitmentControlAgent:
    def stress_test(self, deal: ProposedDeal) -> CommitmentVerdict:
        base = deal.acv
        indexed = base * deal.indexed_share * (1 + deal.assumed_index_pct)
        scenarios = {
            "+5%": indexed * 1.05,
            "+10%": indexed * 1.10,
            "+15%": indexed * 1.15,
        }
        verdict = self._evaluate_tolerance(scenarios, deal.entity_margin_tolerance)
        return CommitmentVerdict(scenarios=scenarios, verdict=verdict)
```

Files: `apps/web/app/(dashboard)/commitment-check/`, `apps/api/app/agents/commitment_control.py`, `apps/api/app/api/v1/commitment_check.py`

### 10.2 Multi-entity Portfolio Governance
- Full group-level Portfolio module: consolidation across all entities
- Cross-entity opportunity identification (same vendor → multi-entity leverage)
- Per-entity P&L impact view

### 10.3 External Intelligence Seam
Per §3.4, external benchmarks are explicitly out of scope for v1–v3. This phase creates the clean integration seam:
- `apps/api/app/connectors/external/` directory with `ExternalBenchmarkBase` ABC
- UI labels "requires external data" endpoints behind a feature flag
- No implementation of external data — only the interface and flag

### Key tasks
- [ ] Build Commitment Check module UI (deal input form + stress test results + verdict)
- [ ] Build Commitment Control agent
- [ ] Extend Portfolio module with cross-entity consolidation view
- [ ] Add cross-entity opportunity detection (same vendor, multiple entities)
- [ ] Create `ExternalBenchmarkBase` ABC (no-op implementation; feature-flagged UI labels)
- [ ] Performance test at scale: seed 10M spend records; verify < 5s dashboard load from memory

---

## Cross-cutting Concerns (all phases)

### Security (applies from Phase 0)
- Row-level security on all tables: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`
- Auth0 JWT validation on every API endpoint
- PII redaction in `ModelGateway` before every LLM call
- Contract text treated as untrusted (sandbox in extraction agent)
- Allowlisted tool use in all LangGraph agents

### Performance (applies from Phase 4)
- All dashboard reads from `TenantMemory` Redis cache (< 5s target)
- Conversational queries from pgvector + memory (< 3s target)
- ClickHouse for any query scanning > 1M rows
- Agent workloads partitioned by tenant; Celery concurrency configurable

### Observability (Phase 0 scaffold; Phase 9 production-grade)
- OpenTelemetry traces on all API requests and agent runs
- Per-agent dashboards: success rate, confidence distribution, latency, model cost
- AgentRun table as audit log (every phase writes to it from Phase 4 onward)
- Golden dataset regression evals run on every model/prompt change (GitHub Actions)

### Testing strategy
- Unit tests: all detection rules, matching logic, scoring formulas
- Integration tests: full ingestion → matching → detection → memory pipeline on synthetic dataset
- Eval harnesses: matching precision/recall, answer faithfulness, extraction accuracy
- Load tests: 10M spend records benchmark before Phase 10 ship

---

## Phase Summary Table

| Phase | Delivers | Key Agents | Duration |
|-------|---------|-----------|---------|
| 0 | Foundation: monorepo, DB schema, auth, CI | — | 1–2 wks |
| 1 | Google Sheets ingestion + vendor normalization | Ingestion | 2–3 wks |
| 2 | Spend↔contract matching + confidence scoring | Matching | 2 wks |
| 3 | Detection rule engine (7 rules) + opportunities | Detection, Recommendation | 2 wks |
| 4 | Ingest-once memory layer + audit log | All (AgentRun logging) | 1–2 wks |
| 5 | Core UI modules (Dashboard, Contracts, Renewals, Recovery, Data Quality, Assessment) | — | 4–5 wks |
| 6 | NirvanaI: Q&A + document generation | Assistant, Document/Action | 3 wks |
| 7 | Vendors, Indexation, Portfolio + advanced agents | Enrichment, Extraction, Anomaly, Data Steward | 3–4 wks |
| 8 | v1.5: above-rate, volume-tier, line-item recovery | Detection (extended) | 3 wks |
| 9 | v2: workflow automation, ERP connectors, learning loop | Workflow Automation | 4–5 wks |
| 10 | v3: Commitment Check, multi-entity portfolio, external seam | Commitment Control | 3–4 wks |
| **Total** | | | **~28–37 wks** |

---

## Agent Rollout Sequence (per §15.1)

### Wave 1 (Phases 1–4): Deterministic agents — high trust, code-heavy
- Ingestion agent, Matching agent, Detection agent

### Wave 2 (Phases 5–7): Generative assist — human-reviewed
- Recommendation agent, Contract Extraction agent, NirvanaI Assistant, Document/Action agent, Enrichment agent

### Wave 3 (Phases 8–10): Automation — behind approvals, evals-gated
- Workflow Automation agent (L3), Commitment Control agent, Anomaly ML models, learning feedback loop
