# Terzo Cost Intelligence

AI-agent-driven platform that maps enterprise spend to contracts to recover margin and govern commitments.

Built phase-by-phase. The single source of truth for architecture is
[`Docs/Cost Intelligence - Full Architecture.md`](Docs/Cost%20Intelligence%20-%20Full%20Architecture.md);
the build plan / task checklist is [`Docs/2026-06-21-cost-intelligence-platform.md`](Docs/2026-06-21-cost-intelligence-platform.md).

## Status

| Phase | Scope | State |
| ----- | ----- | ----- |
| **0 — Foundation & Infrastructure** | Monorepo, multi-tenant Postgres + RLS, Auth0, immutable audit, Docker Compose, CI, OTel | ✅ implemented |
| 1 — Data Ingestion & Google Sheets | Connector framework, data contracts, Ingestion agent | ⬜ next |
| 2–10 | Matching → Detection → Memory → UI → NirvanaI → … | ⬜ planned |

## Layout

```
cost-intelligence/
├── apps/
│   ├── api/                 # FastAPI backend (Python 3.12, async SQLAlchemy)
│   └── web/                 # Next.js 14 frontend (App Router, TS, Tailwind)
├── packages/                # shared TS types, detection-rule specs (later phases)
├── migrations/              # Alembic (001 = foundation schema + RLS)
├── infra/                   # Docker Compose, OTel collector, Terraform outline
├── evals/                   # eval harness placeholder (populated Phase 2+)
├── pyproject.toml           # uv project (backend deps)
├── pnpm-workspace.yaml      # JS workspace
└── Docs/                    # architecture (source of truth) + plan + blueprint
```

## Prerequisites

| Tool | Version | For |
| ---- | ------- | --- |
| Python | 3.12+ | backend |
| [uv](https://docs.astral.sh/uv/) | latest | Python deps/venv |
| Node | 20+ | frontend |
| pnpm | 9+ | JS workspace |
| Docker | latest | local Postgres/Redis/ClickHouse/OTel |

## Quickstart

```bash
cp .env.example .env                       # fill Auth0 + secrets

# infra
docker compose -f infra/docker-compose.yml up -d postgres redis

# backend
uv sync                                    # creates .venv, installs deps
uv run alembic upgrade head                # apply migration 001
uv run uvicorn app.main:app --reload --port 8000   # run from apps/api OR with PYTHONPATH=apps/api

# frontend
pnpm install
pnpm --filter web dev                      # http://localhost:3000

# tests (unit + api). Integration RLS tests need a live Postgres:
uv run pytest apps/api -q
RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration -q
```

Liveness: `curl localhost:8000/healthz` → `{"status":"ok",...}`.

## Architecture invariants (all phases)

- **Tenant isolation** — Postgres RLS keyed on `app.current_tenant`; `FORCE`d on every tenant table; fail-closed (no context ⇒ zero rows).
- **Immutable audit** — `agent_runs` (no DELETE; terminal runs frozen by trigger) and `audit_events` (no UPDATE/DELETE).
- **Tenant identity is never client-supplied** — only from a verified Auth0 JWT claim.
- **Determinism for money** — all dollar math in Python; never in an LLM (enforced from Phase 3+).

See the Phase 0 section of the architecture doc for the full design + Definition of Done.
