# Phase Manifest — which files belong to which phase

The code is organized **by responsibility** (`core/`, `models/`, `services/`,
`agents/`, `connectors/`, …) per Python/monorepo convention — not by phase, so
imports stay clean and later phases build on earlier ones. This manifest gives
the phase view: which phase introduced (or extended) each file.

Legend: **NEW** = introduced this phase · **EXT** = extended this phase (introduced earlier).

Source of truth for design: [`Cost Intelligence - Full Architecture.md`](Cost%20Intelligence%20-%20Full%20Architecture.md).
Verification reports: [`../PHASE_0_REPORT.md`](../PHASE_0_REPORT.md), [`../PHASE_1_REPORT.md`](../PHASE_1_REPORT.md), [`../PHASE_2_REPORT.md`](../PHASE_2_REPORT.md), [`../PHASE_3_REPORT.md`](../PHASE_3_REPORT.md), [`../PHASE_4_REPORT.md`](../PHASE_4_REPORT.md), [`../PHASE_5_REPORT.md`](../PHASE_5_REPORT.md), [`../PHASE_6_REPORT.md`](../PHASE_6_REPORT.md), [`../PHASE_7_REPORT.md`](../PHASE_7_REPORT.md), [`../PHASE_8_REPORT.md`](../PHASE_8_REPORT.md), [`../PHASE_9_REPORT.md`](../PHASE_9_REPORT.md), [`../PHASE_10_REPORT.md`](../PHASE_10_REPORT.md).

---

## Phase 0 — Foundation & Infrastructure

Monorepo scaffold, multi-tenant Postgres + RLS, Auth0, immutable audit log, Docker/CI/OTel.

### Repo root (NEW)
```
package.json · pnpm-workspace.yaml · pyproject.toml · alembic.ini
.gitignore · .env.example · README.md
.github/workflows/ci.yml
infra/docker-compose.yml · infra/otel-collector.yaml · infra/terraform/README.md
packages/shared-types/{package.json,index.d.ts} · packages/detection-rules/README.md
evals/{README.md,run_evals.py}
```

### Backend — `apps/api` (NEW)
```
Dockerfile · app/__init__.py · app/main.py
app/core/{__init__,config,database,tenancy,auth,rbac,audit,logging,otel}.py
app/models/{__init__,base,tenant,entity,role,user,agent_run,audit_event}.py
app/schemas/{__init__,health,me,auth}.py
app/api/{__init__}.py · app/api/v1/{__init__,health_routes,me_routes,auth_routes}.py
app/services/{__init__,user_service}.py
app/workers/__init__.py
migrations/{env.py,script.py.mako} · migrations/versions/001_initial_schema.py
```

### Tests (NEW)
```
tests/__init__.py · tests/conftest.py
tests/{test_settings,test_rbac,test_api}.py
tests/integration/{__init__,test_foundation_db}.py
```

### Frontend — `apps/web` (NEW)
```
package.json · tsconfig.json · next.config.mjs · tailwind.config.ts
postcss.config.mjs · .eslintrc.json · next-env.d.ts · Dockerfile
app/globals.css · app/layout.tsx · app/page.tsx
app/(auth)/login/page.tsx · app/api/auth/[...auth0]/route.ts
app/(dashboard)/layout.tsx · app/(dashboard)/dashboard/page.tsx
middleware.ts · lib/{api,auth,api.test}.ts
```

---

## Phase 1 — Data Ingestion & Google Sheets Connector

Connector framework, 95-field canonical model, data contracts, vendor normalization,
the deterministic Ingestion LangGraph agent, idempotent UPSERT, Redis events.

### Backend — models (NEW)
```
app/models/vendor.py      # Vendor, VendorAlias
app/models/contract.py    # Contract (95+ fields), ContractLineItem, ContractClause
app/models/spend.py       # SpendRecord
app/models/invoice.py     # Invoice, InvoiceLineItem
app/models/staging.py     # DataSource, IngestionBatch, StagedRecord
app/models/__init__.py    # EXT — registers the Phase 1 models
app/models/base.py        # EXT — datetime → TIMESTAMPTZ mapping
```

### Backend — schemas / connectors / services / agent / workers (NEW)
```
app/schemas/data_contracts.py  · app/schemas/data_sources.py
app/connectors/{__init__,base,oauth,google_sheets,registry}.py
app/services/{vendor_normalization,ingestion_persistence,events}.py
app/core/secrets.py
app/agents/{__init__,ingestion}.py
app/workers/ingestion_tasks.py
app/api/v1/{data_sources_routes,staging_routes,google_sheets_routes}.py
migrations/versions/002_ingestion_schema.py
```

### Backend — extended (EXT)
```
app/core/config.py   # Google/OAuth/ingestion settings
app/core/database.py # NullPool in test env
app/main.py          # mount data-sources / staging / google-sheets routers
```

### Tests (NEW)
```
tests/{test_data_contracts,test_ingestion_unit}.py
tests/integration/test_ingestion.py
```

### Frontend (NEW)
```
app/(dashboard)/settings/data-sources/page.tsx
```

---

## Phase 2 — Spend↔Contract Matching Engine

PO-exact + weighted-fuzzy + AI-inference matching, confidence scoring, maverick
queue, human override, eval harness.

### Backend — models / migration (NEW)
```
app/models/matching.py            # MatchResult, UnmatchedQueue
app/models/__init__.py            # EXT — registers the matching models
migrations/versions/003_matching.py
```

### Backend — services / gateway / agent / worker / API (NEW)
```
app/services/matching.py          # MatchingService (PO, fuzzy, override, full rematch)
app/services/matching_candidates.py
app/services/matching_lineage.py  # confidence propagation seam (→ Phase 3)
app/core/model_gateway.py         # minimal LLM chokepoint (Phase 6 expands)
app/agents/matching.py            # LangGraph agent + AI-inference node (0.80 cap)
app/workers/matching_tasks.py
app/schemas/matching.py
app/api/v1/match_results_routes.py
app/main.py                       # EXT — mount match-results router
evals/matching/eval_harness.py · evals/matching/golden/golden_pairs.jsonl
```

### Tests (NEW)
```
tests/test_matching_unit.py
tests/integration/test_matching.py
```

---

## Phase 3 — Detection Rule Engine

8 v1 leakage/savings/control rules, Opportunity entity, scoring, lifecycle state
machine, cited rationale agent, ~$241K eval parity.

### Backend — models / migration (NEW)
```
app/models/opportunity.py         # Opportunity, RecoveryItem
app/models/__init__.py            # EXT — registers the detection models
migrations/versions/004_detection.py
```

### Backend — rules / services / agents / worker / API (NEW)
```
app/services/rules/_types.py + {maverick,unused_commitment,overspend,auto_renewal,
    uplift_creep,post_expiry,duplicate_invoice,missing_invoice}.py
app/services/detection.py · app/services/scoring.py · app/services/opportunity_status.py
app/agents/detection.py · app/agents/recommendation.py
app/workers/detection_tasks.py
app/schemas/opportunity.py · app/api/v1/opportunities_routes.py
app/main.py                       # EXT — mount opportunities + detection routers
evals/detection/eval_harness.py · evals/detection/golden/synthetic_dataset.json
```

### Tests (NEW)
```
tests/test_detection_rules.py
tests/integration/test_detection.py
```

---

## Phase 4 — Agent Memory Layer ("Ingest-Once, Operate-from-Memory")

Three-store memory (Postgres `tenant_memory` = truth, pgvector `contract_embeddings`,
Redis KPI cache), deterministic KPI compute, the full sync pipeline, the AgentRun
lifecycle retrofit, and the sync / agent-runs APIs.

### Backend — models / migration (NEW)
```
app/models/memory.py              # TenantMemory (Store 1), ContractEmbedding (Store 2), SyncRun
app/models/__init__.py            # EXT — registers the memory models
migrations/versions/005_memory_layer.py   # 3 tables, fail-closed RLS+FORCE, ivfflat ANN index
```

### Backend — services / core / pipeline / API (NEW)
```
app/services/memory_kpis.py       # KpiComputer — every KPI in Python Decimal (§5.6)
app/services/memory.py            # MemoryService — build / get_kpis / mark_stale / refresh / invalidate
app/services/embeddings.py        # EmbeddingsService — lazy voyage-3 (skips without key)
app/services/sync.py              # SyncService — one-running-sync guard + lifecycle
app/core/kpi_cache.py             # RedisKpiCache — versioned Store 3
app/core/redis.py                 # loop-safe async client factory
app/core/agent_run.py             # agent_run ctx-mgr + audited_agent decorator (§5.4 retrofit)
app/core/snapshots.py             # S3SnapshotStore — best-effort inputs/outputs snapshots
app/workers/sync_tasks.py         # run_full_sync_async pipeline + Celery initial/refresh tasks
app/schemas/sync.py
app/api/v1/sync_routes.py         # POST /sync/initial, POST /sync/refresh, GET /sync/status
app/api/v1/agent_runs_routes.py   # GET /agent-runs (paginated/filterable), GET /agent-runs/{id}
app/main.py                       # EXT — mount sync + agent-runs routers
```

### Backend — extended (EXT)
```
app/core/config.py   # memory/embedding/ivfflat/agent-run/snapshot settings
```

### Tests (NEW)
```
tests/integration/test_memory.py  # build/KPIs, Redis+fallback, stale, agent-run lifecycle, sync guard, RLS
```

---

## Phase 5 — Core Application Modules (v1 UI)

7 modules (Dashboard, Opportunity Assessment, Spend Explorer, Contracts, Renewals,
Margin Recovery, Data Quality) over a shared DashboardShell. Backend is **read
models** over the Phase-4 memory layer + canonical drill-downs (no new tables).

### Backend — read models / schemas / routers (NEW)
```
app/services/read_models.py       # ReadModelService — memory aggregates + canonical drill-downs
app/schemas/read_models.py        # Pydantic v2 response shapes (§4.2)
app/api/v1/deps.py                # get_read_models dependency
app/api/v1/dashboard_routes.py    # GET /dashboard/kpis
app/api/v1/spend_routes.py        # GET /spend/by-vendor|by-category|by-cost-center|trend|match-coverage
app/api/v1/contracts_routes.py    # GET /contracts, /contracts/{id}, /contracts/{id}/spend
app/api/v1/renewals_routes.py     # GET /renewals?window=
app/api/v1/recovery_routes.py     # GET /recovery/packs, /recovery/{id}
app/api/v1/data_quality_routes.py # GET /data-quality/coverage, /data-quality/events
app/main.py                       # EXT — mount the 6 read routers
# Opportunity workflow endpoints (status/assign) reused from Phase 3, surfaced here.
```

### Frontend — `apps/web` (NEW)
```
app/(dashboard)/layout.tsx        # EXT — DashboardShell (sidebar/topbar/nirvana panel)
app/(dashboard)/{dashboard,assessment,spend,contracts,contracts/[id],renewals,recovery,data-quality}/page.tsx
components/shell/{sidebar,topbar,tenant-switcher,user-menu,sync-status-badge,sync-status-banner}.tsx
components/nirvana/nirvana-panel.tsx
components/ui/{button,tabs}.tsx
components/modules/dashboard/{kpi-tile,opportunity-chart,alerts-panel,onboarding-empty-state}.tsx
components/modules/assessment/{assessment-client,status-workflow,status-badge,owner-select}.tsx
components/modules/spend/{spend-explorer-client,spend-bar-chart,spend-trend-chart,match-coverage-donut}.tsx
components/modules/contracts/{utilization-bar,indexation-badge,linked-spend-table,contract-fields}.tsx
components/modules/renewals/{renewals-client,renewal-row}.tsx
components/modules/recovery/recovery-pack-card.tsx
components/modules/dq/{coverage-gauge,review-queue-client}.tsx
lib/{design-tokens,modules,format,types,config,cn,providers}.ts(x)  · lib/hooks/{use-opportunities,use-spend,use-renewals}.ts
lib/api.ts                        # EXT — apiServer/apiClient added
app/globals.css · tailwind.config.ts  # EXT — Terzo token layer over shadcn
package.json                      # EXT — @tanstack/react-query, recharts, lucide-react
```

### Tests (NEW)
```
tests/integration/test_read_models.py  # 8 read-model API tests (§14.3)
```

---

## Phase 6 — NirvanaI Conversational Assistant

Grounded Q&A + document drafting over the Phase-4 memory/pgvector store, mounted into
the Phase-5 shell. All LLM calls (Google Gemini) flow through the single ModelGateway;
every dollar figure is groundedness-validated; drafts are human-gated.

### Backend — models / migration (NEW)
```
app/models/nirvana.py             # NirvanaConversation, NirvanaMessage, DocumentDraft, ModelUsageEvent
app/models/memory.py              # EXT — ContractEmbedding→MemoryEmbedding (memory_embeddings + source/source_id)
app/models/__init__.py            # EXT — registers Phase 6 models
migrations/versions/006_nirvana.py # 4 tables (fail-closed RLS; model_usage append-only);
                                   # contract_embeddings→memory_embeddings + HNSW ANN index
```

### Backend — gateway / services / agent / API (NEW)
```
app/core/model_gateway.py         # EXT — full ModelGateway (routing, cache, cost, redaction, budget)
app/services/usage.py             # record_model_usage (append-only cost attribution)
app/services/rag.py               # RAGService — RBAC/entity-scoped pgvector retrieval + rerank
app/services/groundedness.py      # GroundednessValidator — the $-figure enforcement gate
app/services/documents.py         # 5 templates + RBAC-scoped context assembly
app/services/conversation.py      # turn persistence + history
app/agents/prompts.py             # intent/QA/groundedness prompts + 5 doc skeletons
app/agents/nirvana.py             # LangGraph: classify→qa(retrieve/generate/validate)/document/out_of_scope
app/agents/{matching,recommendation}.py  # EXT — migrated to the new gateway API
app/schemas/nirvana.py · app/api/v1/nirvana_routes.py
app/main.py                       # EXT — mount the nirvana router
app/core/config.py                # EXT — model gateway / RAG / groundedness settings
```

### Frontend — `apps/web` (NEW)
```
components/nirvana/{chat-panel,message-bubble,document-preview}.tsx
components/nirvana/nirvana-panel.tsx  # EXT — mounts the live ChatPanel (was a placeholder)
lib/hooks/use-nirvana.ts · lib/types.ts  # EXT — NirvanaI types
```

### Tests (NEW)
```
tests/test_nirvana_unit.py            # 7 unit (groundedness, gateway routing/cost/redaction, templates)
tests/integration/test_nirvana.py     # 3 integration (RAG RBAC scope, rate-limit, human-gated draft audit)
```

---

## Phase 7 — Advanced Modules & Agents

Vendors / Indexation / Portfolio modules + the generative-assist agent wave (Enrichment,
Contract Extraction sandbox, statistical Anomaly, Data Steward). All $ math in Python;
extracted terms + figure-affecting fixes are human-gated.

### Backend — models / migration (NEW)
```
app/models/advanced.py            # ExtractionQueueItem, AnomalyFlag, StewardProposal, IndexRegisterEntry
app/models/spend.py               # EXT — taxonomy_l1/l2, base_amount, fx_rate, enrichment_confidence
app/models/__init__.py            # EXT — registers Phase 7 models
migrations/versions/007_advanced.py  # 4 RLS tables + 5 spend_records enrichment columns
```

### Backend — services / agents / API (NEW)
```
app/services/vendors.py           # rollup + consolidation fragmentation_score
app/services/indexation.py        # first-party exposure (ACV × indexed_share × assumed_move)
app/services/portfolio.py         # RBAC-gated multi-entity rollup
app/services/anomaly_detection.py # Z-score / IQR / new-vendor / dup-payment (pure Python)
app/services/taxonomy.py          # L1/L2 rules-first + LLM fallback
app/services/currency.py          # first-party FX normalization
app/agents/extraction.py          # untrusted-input sandbox → verification queue (never canonical)
app/agents/enrichment.py · app/agents/anomaly.py · app/agents/data_steward.py
app/agents/prompts.py             # EXT — sandbox/extraction/taxonomy/steward prompts
app/schemas/advanced.py
app/api/v1/{vendors,indexation,portfolio,extraction,anomalies,data_steward}_routes.py
app/main.py · app/core/config.py  # EXT — mount routers; anomaly/consolidation/verify settings
```

### Frontend — `apps/web` (NEW)
```
app/(dashboard)/{vendors,indexation,portfolio,extraction}/page.tsx
components/modules/indexation/exposure-slider.tsx
components/modules/extraction/verification-queue.tsx
lib/modules.ts · lib/types.ts     # EXT — vendors/indexation/portfolio nav enabled + types
```

### Tests (NEW)
```
tests/test_advanced_unit.py           # 7 unit (detectors, taxonomy rules, extraction schema, steward gate)
tests/integration/test_advanced.py    # 4 integration (consolidation, exposure, portfolio RBAC, extraction verify)
```

---

## Phase 8 — v1.5 Line-Item Depth & Recovery

Above-rate + volume-tier line-item recovery rules (pure Python), rate-card extraction
behind a HITL verify gate, header↔line coexistence dedup, and per-line recovery packs.

### Backend — models / migration (NEW/EXT)
```
app/models/rate_card.py           # ContractRateCard, RateCardTier
app/models/opportunity.py         # EXT — coexistence cols; RecoveryPack; per-line RecoveryItem cols
app/models/invoice.py             # EXT — InvoiceLineItem analysis cols (line_number/raw_sku/contract_id/rate_card_id)
app/models/__init__.py            # EXT — registers Phase 8 models
migrations/versions/008_line_item_depth.py
```

### Backend — rules / services / API (NEW)
```
app/services/rules/above_rate.py · app/services/rules/volume_tier.py   # pure recovery rules
app/services/rate_card.py · app/services/coexistence.py · app/services/recovery_pack.py
app/services/sku_normalization.py · app/services/line_item_detection.py · app/services/rate_card_extraction.py
app/schemas/line_item.py · app/core/config.py (EXT)
app/api/v1/rate_cards_routes.py · app/api/v1/line_items_routes.py · app/main.py (EXT)
```

### Frontend — `apps/web` (NEW)
```
app/(dashboard)/rate-cards/page.tsx
components/modules/rate-cards/rate-card-verification-queue.tsx · lib/types.ts (EXT)
```

### Tests (NEW)
```
tests/test_line_item_unit.py            # 9 unit (above_rate, volume_tier, coexistence)
tests/integration/test_line_item_pipeline.py  # 2 integration (verify gate, end-to-end pipeline)
```

---

## Phase 9 — v2 Agentic Automation, ERP Connectors & Continuous Learning

Gated workflow automation (human-in-the-loop), ERP connectors (Coupa/Oracle/SAP), an event bus, ML anomaly detection with statistical fallback, and a deterministic continuous-learning loop. **No irreversible external action without explicit human approval (§5.1).**

### Backend — models / migration (NEW/EXT)
```
app/models/automation.py          # Task, ApprovalGate, TaskReminder, ConnectorCredential, LearningLabel, ModelCalibration
app/models/__init__.py            # EXT — registers Phase 9 models
app/core/config.py                # EXT — workflow/learning/anomaly/event-bus settings
migrations/versions/009_agentic_automation.py   # 6 tables + NULLIF/FORCE RLS + append-only rules
```

### Backend — services / agent / connectors / API (NEW/EXT)
```
app/services/task.py · app/services/workflow.py · app/services/external_actions.py
app/services/feedback_loop.py · app/services/anomaly_ml.py
app/agents/workflow_automation.py    # LangGraph gated flow — NO external-send node
app/core/eventbus.py                 # EventBus ABC; Redis / Kafka(lazy) / DualWrite
app/connectors/erp/{__init__,base,mappers,coupa,oracle,sap}.py
app/connectors/registry.py           # EXT — coupa/oracle/sap source types
app/api/v1/tasks_routes.py · app/api/v1/learning_routes.py · app/main.py (EXT)
```

### Frontend — `apps/web` (NEW/EXT)
```
app/(dashboard)/tasks/page.tsx
components/modules/tasks/task-approval-queue.tsx
lib/modules.ts (EXT — "Workflow Tasks" nav) · lib/types.ts (EXT)
```

### Tests (NEW)
```
tests/test_workflow_unit.py                   # 8 unit (gate, ERP mappers, anomaly fallback, dual-write, learning math)
tests/integration/test_workflow_pipeline.py   # 8 integration (gated approve/reject, executor guard, state machine, sparse learning)
```

---

## Phase 10 — v3 Commitment Check & Portfolio Governance

Pre-signature control (advisory stress test; human signs), multi-entity portfolio governance, the first-party external-intelligence seam (interface-only, flag off), and the scalability/degradation framing (partitioning, tiering, quotas, circuit breakers). All stress-test math is Python; the seam is never wired.

### Backend — models / migration (NEW/EXT)
```
app/models/commitment.py          # CommitmentCheck, PortfolioRollup, TenantQuota, SpendTierMetadata
app/models/__init__.py            # EXT — registers Phase 10 models
app/core/config.py                # EXT — commitment / external-seam / tiering / quota / NFR settings
migrations/versions/010_control_layer.py   # 4 tables + NULLIF/FORCE RLS + commitment no-delete rule
```

### Backend — agent / services / seam / ops / API (NEW/EXT)
```
app/agents/commitment_control.py · app/schemas/commitment.py · app/services/commitment.py
app/services/portfolio.py (EXT — PortfolioGovernanceService)
app/connectors/external/{__init__,base}.py   # ExternalBenchmarkBase ABC (seam, interface only)
app/core/external_guard.py · app/core/quotas.py · app/core/degradation.py
app/services/partitioning.py · app/services/tiering.py · app/services/clickhouse_history.py
app/api/v1/commitment_routes.py · app/api/v1/admin_routes.py
app/api/v1/portfolio_routes.py (EXT) · app/api/v1/health_routes.py (EXT — /health/degradation)
app/main.py (EXT)
```

### Frontend — `apps/web` (NEW/EXT)
```
app/(dashboard)/commitment/page.tsx · components/modules/commitment/commitment-check-form.tsx
components/ui/badge.tsx · components/RequiresExternalData.tsx
app/(dashboard)/portfolio/page.tsx (EXT — vendor-leverage)
lib/modules.ts (EXT — Commitment Check live) · lib/types.ts (EXT)
```

### Tests / load harness (NEW)
```
tests/test_commitment_unit.py                  # 12 unit (math, verdicts, seam, breaker, tiering, partitions)
tests/integration/test_commitment_pipeline.py  # 8 integration (API, sign 409, RBAC, leverage, degradation, immutability)
evals/load/test_10m_rows.py                    # gated 10M-row capstone (RUN_LOAD_TESTS=1)
```

> **Deferred to a maintenance migration:** the destructive online conversion of `spend_records`
> to a declaratively partitioned table (§4.1/§10.1). `PartitionManager` generates the DDL;
> `spend_tier_metadata` tracks hot/warm/cold bookkeeping. The 10M-row NFR proof is the gated
> load harness above. The external-intelligence seam stays **interface-only and flag-off**.

> Migration files are numerically phase-ordered (`001`=P0, `002`=P1, …), so the
> `migrations/versions/` directory already reads as a phase timeline.
