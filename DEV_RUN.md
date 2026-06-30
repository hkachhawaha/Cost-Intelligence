# Local end-to-end demo (no Auth0 required)

> **The product is the Cost Intelligence app at `/` → `/ci`** (single-workspace, Google-Sheets-driven,
> matching the v2 prototype). Start the API + web (below), then open **http://localhost:3000** and,
> if no data shows, go to **Settings → Connect Spreadsheet** (the Nexus URL is pre-filled).
> Run the API with `NEXT_PUBLIC_DEV_AUTH=1` on the web side and `DEV_AUTH_BYPASS=true` on the API.


Run the whole platform locally and click through every module with seeded data. This uses a
**local-only auth bypass** that is platform-refused in production (`is_production` guard +
explicit flags). Never set these flags in a deployed environment.

## Prerequisites
- Postgres 17 + pgvector and Redis running (e.g. `docker compose -f infra/docker-compose.yml up -d postgres redis`)
- Migrations applied: `uv run --project apps/api alembic upgrade head`
- `uv` and Node installed; from `apps/web`: `npm install`

## 1. Seed the demo tenant
From the repo root (so `.env` is loaded):
```bash
uv run --project apps/api python apps/api/scripts/seed_demo.py
```
Creates 1 tenant (2 entities, 3 vendors, 3 contracts, invoices, spend), runs
matching → detection → memory build, and opens one approval task. Re-run anytime — it wipes
the demo tables first (local DB only). Seeds ~9 opportunities (~$141k identified), a CloudCo
multi-entity leverage signal, an unverified rate card, and a pending workflow task.

## 2. Start the API (auth bypassed)
From `apps/api`:
```bash
ENVIRONMENT=local DEV_AUTH_BYPASS=true \
  uv run uvicorn app.main:app --port 8000 --reload
```
Startup logs a loud `dev_auth_bypass_ENABLED` warning. Every request now runs as the demo
admin principal for the seeded tenant — no token needed. (Add `GEMINI_API_KEY=…` to get LLM
narration on NirvanaI / commitment rationale; without it those degrade gracefully.)

## 3. Start the web app (auth bypassed)
From `apps/web`:
```bash
NEXT_PUBLIC_DEV_AUTH=1 NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1 npm run dev
```
Open **http://localhost:3000** → lands straight on the dashboard (no login).

## What to click
- **Dashboard** — KPIs (total spend, under-management %, identified savings/recovery).
- **Opportunity Assessment** — the detected opportunities, ranked.
- **Spend Explorer / Contracts / Renewals / Recovery / Data Quality** — read models.
- **Vendors / Indexation / Portfolio** — portfolio shows the CloudCo multi-entity leverage candidate.
- **Rate Cards** — the unverified card in the verification queue (verify it → drives line-item math).
- **Workflow Tasks** — the pending auto-renewal task; **Approve** fires the gated external action.
- **Commitment Check** — enter a proposed deal (e.g. ACV 1.2M, indexed share 0.60, index 3%,
  tolerance 800k) → ±5/10/15% stress table + advisory verdict; sign it.

## Quick API smoke (no UI)
```bash
curl localhost:8000/api/v1/dashboard/kpis
curl localhost:8000/api/v1/portfolio/vendor-leverage
curl -X POST localhost:8000/api/v1/commitment-check -H 'content-type: application/json' \
  -d '{"vendor_name":"CloudCo","acv":"1200000.00","indexed_share":"0.60","assumed_index_pct":"0.03","margin_tolerance":"800000.00"}'
```
Or browse the OpenAPI docs at **http://localhost:8000/docs**.

## Safety
- The bypass activates only when `DEV_AUTH_BYPASS=true` **and** `ENVIRONMENT != prod`; in prod it
  is refused regardless. The seed refuses to run when `ENVIRONMENT=prod`.
- `NEXT_PUBLIC_DEV_AUTH=1` only affects the local web build; unset it for any real deployment.
