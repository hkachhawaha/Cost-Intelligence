# Phase 4 — Agent Memory Layer ("Ingest-Once, Operate-from-Memory"): Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 4, §5.8) and **verified** against Python 3.12 + PostgreSQL 17 (pgvector) + Redis.

## Verification results ✅

| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Typecheck | `uv run mypy apps/api/app` | ✅ no issues in **94 files** |
| Migration | `uv run alembic upgrade head` (004 → 005) | ✅ clean (tenant_memory, contract_embeddings, sync_runs) |
| Schema audit | RLS enabled+forced on all 3 tables; ivfflat ANN index present | ✅ verified via `pg_class` / `pg_indexes` / `pg_policies` |
| Phase 4 suite | `RUN_DB_TESTS=1 uv run pytest .../test_memory.py` | ✅ **6 passed** |
| **Full suite** | `RUN_DB_TESTS=1 uv run pytest apps/api/tests` | ✅ **59 passed** |

### Phase 4 test breakdown

```
test_memory_build_computes_kpis ................. PASSED  (KPIs deterministic; version bumps on rebuild)
test_get_kpis_redis_then_postgres_fallback ...... PASSED  (Redis hot path; Postgres fallback when cold)
test_mark_stale_keeps_intelligence .............. PASSED  (banner raised, figures survive)
test_agent_run_lifecycle ........................ PASSED  (running → completed | failed)
test_sync_single_running_guard .................. PASSED  (one running sync per tenant)
test_memory_rls_isolation ....................... PASSED  (non-superuser role sees only its tenant)
6 passed
```

### KPI determinism fixture (asserted exactly)

A 2-contract / 2-spend / 2-opportunity tenant where one contract is active+in-range and one is expired+out-of-range:

```
total_spend                100,000.00   match_coverage_pct          100.00   (both spend rows matched)
total_savings               30,000.00   spend_under_management_pct   60.00   (only S1 → active contract)
total_recovery              20,000.00   contract_compliance_pct      60.00   (S2 spend date outside term)
total_identified            50,000.00   opportunity_count                 2
```

Every figure is computed in Python `Decimal` by `KpiComputer` — never an LLM (§5.6).

## What was built

| Area | Files |
| ---- | ----- |
| Config | `core/config.py` — Phase 4 block (`memory_cache_ttl_seconds`, `embedding_model/_dim/_batch_size`, `embedding_fatal_to_sync`, `ivfflat_lists`, `agent_run_stuck_minutes`, `snapshot_kms`) |
| Models | `models/memory.py` — `TenantMemory` (Store 1, one row/tenant, all KPIs Decimal + JSONB summary blobs + `kpi_snapshot` + `stale`/`memory_version`/`build_run_id`/`source_fingerprint`), `ContractEmbedding` (Store 2, `Vector(1024)`), `SyncRun` |
| Migration | `005_memory_layer.py` — all 3 tables; fail-closed RLS (`NULLIF` + `FORCE`); ivfflat `vector_cosine_ops` index (`lists=100`); FKs `build_run_id → agent_runs`, `tenant_id → tenants` |
| KPI compute | `services/memory_kpis.py` — `KpiComputer.compute_all` → `ComputedMemory(scalars, summaries)`; headline KPIs, by-type/vendor rollups, renewal calendar, spend trend, match breakdown, data-quality, alerts |
| Memory service | `services/memory.py` — `MemoryService` build (Postgres-then-Redis, version bump) / get_kpis (Redis-first, Postgres fallback) / get_section / mark_stale / is_stale / fingerprint / refresh / invalidate |
| Cache (Store 3) | `core/kpi_cache.py` — `RedisKpiCache` (versioned `kpis:{t}` / `section:{t}:{n}` / `memver:{t}`, TTL safety-net, patch, scan-based invalidate); `core/redis.py` — loop-safe client factory |
| Audit lifecycle | `core/agent_run.py` — `agent_run` async ctx-mgr + `audited_agent` decorator: `running → completed | failed`, confidence/actor/outputs recorded, inputs/outputs snapshotted (best-effort) |
| Snapshots | `core/snapshots.py` — `S3SnapshotStore` (no-op without `s3_bucket`/aioboto3; lazy import) |
| Embeddings | `services/embeddings.py` — `EmbeddingsService.embed_tenant` (lazy `voyageai`; skips cleanly without `VOYAGE_API_KEY`) |
| Sync pipeline | `workers/sync_tasks.py` — `run_full_sync_async` (ingestion → enrichment → matching → detection → build_memory → embed → finalize, each wrapped in `agent_run`); Celery `initial_sync`/`refresh_sync`; `memory.rebuilt` Redis-stream emit |
| Sync service | `services/sync.py` — `SyncService` start (one-running guard → enqueue) / complete / fail / status; `SyncAlreadyRunningError` |
| API | `api/v1/sync_routes.py` — `POST /sync/initial` (202), `POST /sync/refresh` (202), `GET /sync/status` (stale + coverage). `api/v1/agent_runs_routes.py` — `GET /agent-runs` (paginated/filterable), `GET /agent-runs/{id}` |
| Schemas | `schemas/sync.py` — `SyncStartRequest/Response`, `CoverageStats`, `SyncStatusResponse`, `AgentRunOut`, `AgentRunListResponse` |
| Wiring | `main.py` — registered `sync_routes` + `agent_runs_routes` under `/api/v1` |
| Tests | `tests/integration/test_memory.py` (6 tests) |

## DoD highlights met

- **Three-store architecture** (§5.8): Postgres `tenant_memory` is the durable source of truth; `contract_embeddings` (pgvector) is the RAG store; Redis is the disposable, versioned KPI cache. The cache is warmed **after** the Postgres commit so it can never lead the truth.
- **Ingest-once, operate-from-memory**: the full sync pipeline runs ingestion → matching → detection once, then bakes every KPI into one snapshot. UI/agents read the snapshot, not the raw tables.
- **Determinism for money**: every dollar/percentage in `tenant_memory` is computed in Python `Decimal` by `KpiComputer`; no LLM is in the figure path.
- **Graceful degradation**: `get_kpis` is Redis-first and falls back to Postgres on a cache miss/outage (integration-tested by flushing the cache mid-test); embedding failure is non-fatal to the sync (`embedding_fatal_to_sync=False`).
- **Stale-without-discard**: `mark_stale` flips the UI banner while keeping the intelligence intact (no re-ingestion needed until the user triggers a Refresh) — asserted in both Postgres and the cached snapshot.
- **Immutable audit retrofit**: every pipeline stage runs inside an `agent_run` that transitions `running → completed|failed` exactly once (DB guard trigger + DELETE block from Migration 001); confidence and inputs/outputs refs are recorded.
- **One sync per tenant**: `SyncService.start` rejects a concurrent sync with `SyncAlreadyRunningError` **before** enqueuing anything.
- **Fail-closed multi-tenancy**: all 3 new tables have RLS enabled **and forced** with the `NULLIF(current_setting('app.current_tenant',true),'')::uuid` policy; isolation verified through a non-superuser role.
- **Versioned cache**: `memory_version` bumps on every rebuild (monotonic) and is stored alongside the snapshot for cache-coherence; rebuild idempotence of the figures is asserted.

## Faithful deviations

- **In-process pipeline over a Celery multi-task chain.** The spec sketches a per-stage Celery DAG; `run_full_sync_async` orchestrates the stages in one async function (each still wrapped in its own `agent_run`), with durable retry at the Celery task boundary. Simpler version-consistency, and directly testable without a worker. Functionally identical audit trail.
- **S3 snapshots and Voyage embeddings are optional/lazy.** Both no-op cleanly when their credentials/SDKs are absent, so the pipeline and tests run end-to-end in a bare environment; they light up automatically when `S3_BUCKET` / `VOYAGE_API_KEY` are set.
- **`enrichment` stage is a passthrough in v1** (records its own audited run) — the body is swapped in Phase 7.

## Bugs found & fixed during verification

1. **Stale snapshot on rebuild** (real latent bug in `MemoryService.build`). With `expire_on_commit=False`, a `prior` row left in the identity map made the post-upsert `session.get` return the stale (pre-rebuild) object — so `memory_version` never advanced on a second build. Fixed with `get(..., populate_existing=True)` to force a reload after the Core upsert.
2. **`build_run_id` FK** — `tenant_memory.build_run_id → agent_runs.run_id` means a build must run inside a real `memory_build` agent_run (as the production pipeline does); the test was corrected to mirror that rather than passing a synthetic id.
3. **mypy**: `pg_insert(TenantMemory.__table__)` (FromClause) → `pg_insert(TenantMemory)`; `contract_by_id.get(m.contract_id)` guarded for `contract_id is None`; `build` return narrowed with an assert.

## How to reproduce

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/opt/postgresql@17/bin:$PATH"
cd "Cost Intelligence"
uv run alembic upgrade head                       # → 005
uv run ruff check apps/api && uv run mypy apps/api/app
RUN_DB_TESTS=1 uv run pytest apps/api/tests -q     # 59 passed
```

(A git-ignored `.env` supplies test datastore URLs + placeholder Auth0 values; no real secrets.)
