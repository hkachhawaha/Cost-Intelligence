# Phase 1 — Data Ingestion & Google Sheets Connector: Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 1) and **verified end-to-end** against Python 3.12 + PostgreSQL 17 + pgvector + Redis.

## Verification results ✅ (all green)

| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Format | `uv run ruff format --check apps/api` | ✅ 63 files formatted |
| Typecheck | `uv run mypy apps/api` | ✅ no issues in 63 files |
| Migration | `uv run alembic upgrade head` (001 → 002) | ✅ clean (11 new tables) |
| **Backend tests** | `RUN_DB_TESTS=1 uv run pytest apps/api` | ✅ **31 passed** |
| Web typecheck + build | `pnpm --filter web typecheck && build` | ✅ `/settings/data-sources` route added |

### DoD-covering tests (Phase 1)

- `test_ingestion_collapse_quarantine_drift_audit` — ingests a 4-row contract batch: 3 valid rows persist; **"Acme Inc"/"ACME, LLC" collapse to one vendor** (2 vendors, 3 aliases); the bad row is **quarantined** (not dropped); an immutable **AgentRun** (actor=ai, completed) is written; **`records.landed` and `data_quality.schema_drift`** both appear on Redis streams.
- `test_ingestion_idempotent` — re-running the same batch yields **0 inserted / 3 updated** (UPSERT on `(tenant_id, source_id, source_row_hash)`); no duplicates.
- `test_rls_isolation_ingestion` — a non-superuser role sees the tenant's 3 contracts under its own tenant context and **0** under another tenant's.
- `test_migration_002_tables_present` — all 11 tables exist.
- 9 unit tests — data-contract validation (currency/date/amount rules) + vendor fingerprinting + idempotency hashing.

## What was built

| Area | Files |
| ---- | ----- |
| Models | `vendor`, `contract` (95+ fields), `spend`, `invoice`, `staging` (data_sources/batches/staged) |
| Migration | `002_ingestion_schema.py` — 11 tables, fail-closed RLS, GIN/po indexes, idempotency unique index |
| Data contracts | `schemas/data_contracts.py` (InboundContract/Spend/Invoice + validators) |
| Connectors | `connectors/{base,oauth,google_sheets,registry}.py` |
| Services | `vendor_normalization`, `ingestion_persistence` (UPSERT), `events` (Redis Streams), `core/secrets` |
| Agent | `agents/ingestion.py` — full LangGraph graph (L2, deterministic, no LLM) |
| Workers | `workers/ingestion_tasks.py` (run/refresh/quarantine-review) |
| API | `data_sources_routes`, `staging_routes`, `google_sheets_routes` |
| Frontend | `(dashboard)/settings/data-sources/page.tsx` |

## Bugs caught by running the verification — and fixed

1. **RLS policy `::uuid` crash** (carried pattern) — fixed with `NULLIF(...,'')::uuid` (fail-closed) in migration 002, matching the Phase 0 correction.
2. **`ingestion_batches` missing `created_at`** — the ORM `TimestampMixin` expects it; the `RETURNING created_at` failed. Added the column.
3. **Naive vs aware datetime mismatch** — `Mapped[datetime]` mapped to naive `TIMESTAMP` while migrations use `TIMESTAMPTZ`; asyncpg rejected `datetime.now(UTC)`. Fixed globally by mapping `datetime → DateTime(timezone=True)` in the ORM base.
4. **Async engine pool across pytest loops** (`Event loop is closed`) — use `NullPool` when `ENVIRONMENT=test`.
5. **Insert/update misclassification** — `created_at == updated_at` heuristic misfired on conflict-update; switched to Postgres `xmax = 0` (the canonical upsert insert/update signal) + bump `updated_at` on conflict.
6. Minor mypy/type fixes (`cast(Table, ...)`, `literal_column`, `dict[str, Any]`, registry default-config call).

## Faithful deviations from the doc

- `ingestion_persistence.upsert_records` folds unmapped/unknown fields into the `extra` JSONB (the doc's `model_dump()` would otherwise pass stray columns straight to INSERT and fail). Lineage preserved.
- The Ingestion agent emits `schema_drift` from the `emit_landed` node on partial batches (valid rows land **and** drift fires), satisfying the DoD that valid rows are never lost.
- `NULLIF` RLS + `datetime→TIMESTAMPTZ` ORM mapping strengthen correctness without changing the spec's intent.

## Environment note

Verified with brew PostgreSQL 17 + pgvector 0.8.3 + Redis 8, `uv`-managed Python 3.12.13. Docker not available in this sandbox; services run natively. `uv.lock`/`pnpm-lock.yaml` committed for CI `--frozen` installs.
