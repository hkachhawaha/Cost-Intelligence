# Phase 0 — Foundation & Infrastructure: Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 0 section), then **verified end-to-end in a Python 3.12 + PostgreSQL 17 + pgvector environment**.

## Verification results ✅ (all green)

| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Format | `uv run ruff format --check apps/api` | ✅ 38 files formatted |
| Typecheck | `uv run mypy apps/api` | ✅ no issues in 38 files |
| Migration | `uv run alembic upgrade head` (+ downgrade/upgrade cycle) | ✅ clean |
| **Backend tests** | `RUN_DB_TESTS=1 uv run pytest apps/api` | ✅ **18 passed** |
| API boot | `uvicorn app.main:app` → curl | ✅ `/healthz` 200, `/me` 401, `/readyz` 503 degraded (redis down, pg up) |
| Web lint/types/test | `pnpm --filter web {lint,typecheck,test}` | ✅ pass |
| Web build | `pnpm --filter web build` | ✅ routes `/`, `/login`, `/dashboard`, `/api/auth/[...auth0]` |

### The 5 load-bearing DoD tests (all pass)

1. `test_rls_tenant_isolation` — tenant A's session cannot read tenant B's rows.
2. `test_rls_fail_closed` — a session with no tenant context returns **zero** rows.
3. `test_rls_write_check_blocks_other_tenant` — inserting another tenant's row is blocked by `WITH CHECK`.
4. `test_audit_event_immutable` — DELETE/UPDATE on `audit_events` are no-ops; the row persists unchanged.
5. `test_agent_run_no_delete_and_terminal_guard` — `agent_runs` DELETE is a no-op; re-opening a terminal run raises.

Plus `test_schema_present` (6 tables + 7 seeded roles) and 11 unit/API tests.

## Issues found by verification — and fixed

Running the suite (rather than just static checks) caught **three real bugs**:

1. **RLS policy crashed instead of failing closed.** `current_setting('app.current_tenant', true)::uuid` raises `invalid input syntax for type uuid` when the GUC is an empty string. Fixed with `NULLIF(current_setting(...), '')::uuid` — both unset *and* empty now yield NULL → zero rows (true fail-closed).
2. **`ON DELETE CASCADE` ⨯ append-only rule conflict.** The `tenants → agent_runs/audit_events` FK cascade collided with the `DO INSTEAD NOTHING` delete-rule (`referential integrity query … gave unexpected result`). Fixed by making the **audit FKs `NO ACTION`** — immutable audit history is never cascade-deleted (operational `entities`/`users` keep `CASCADE`).
3. **Next.js route collision.** `app/(dashboard)/page.tsx` resolved to `/` (route groups add no segment), colliding with `app/page.tsx`, and the `/dashboard` redirect target didn't exist. Fixed by moving the landing to `app/(dashboard)/dashboard/page.tsx`.

Plus minor lint/type fixes: `datetime.UTC`, `float→Decimal` for the confidence column, precise `Callable[..., Awaitable[Principal]]` dependency type, `tests/__init__.py` for unambiguous module resolution.

## Environment note

Verified locally with `uv`-provisioned **Python 3.12.13** and brew **PostgreSQL 17 + pgvector 0.8.3** (Docker is not available in this sandbox, so `docker compose up` was not exercised — the same services were run natively instead). `uv.lock` and `pnpm-lock.yaml` are generated and committed so CI's `--frozen` installs work.

## Faithful deviations from the doc

1. `pyproject.toml` + `alembic.ini` at repo root (the doc's CI runs alembic from root). `app` stays at `apps/api/app`, importable via `prepend_sys_path`/`pythonpath`.
2. Docker build context = repo root for api/celery so the image sees root `pyproject.toml`.
3. RLS policies use `NULLIF(...,'')` and audit FKs are `NO ACTION` (bug fixes above) — strengthens, not weakens, the doc's security model.
