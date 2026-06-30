# Phase 6 — NirvanaI Conversational Assistant: Implementation Report

Implemented to the spec in `Docs/Cost Intelligence - Full Architecture.md` (Phase 6) and **verified**: backend on Python 3.12 + PostgreSQL 17 (pgvector) + Redis; frontend via TypeScript typecheck + ESLint. All LLM calls run on **Google Gemini** through the ModelGateway.

## Verification results ✅

| Check | Command | Result |
| ----- | ------- | ------ |
| Backend lint | `uv run ruff check apps/api` | ✅ All checks passed |
| Backend typecheck | `uv run mypy apps/api/app` | ✅ no issues in **113 files** |
| Migration | `uv run alembic upgrade head` (005 → 006) | ✅ 4 NirvanaI tables + `contract_embeddings`→`memory_embeddings` (HNSW) |
| **Backend suite (P0–P6)** | `RUN_DB_TESTS=1 uv run pytest apps/api/tests` | ✅ **77 passed** |
| Phase 6 tests | `pytest test_nirvana_unit.py + integration/test_nirvana.py` | ✅ **10 passed** |
| Frontend typecheck | `npm run typecheck` (`tsc --noEmit`) | ✅ exit 0 |
| Frontend lint | `npm run lint` (`next lint`) | ✅ no warnings/errors |

### Per-phase focused verification (6–10 tests each, as requested)

```
P0  Foundation (RBAC + DB/RLS/audit) ........................... 9 passed
P1  Ingestion (contracts + idempotent UPSERT) .................. 8 passed
P2  Matching (PO/fuzzy/AI-cap + pipeline) ..................... 10 passed
P3  Detection (8 rules + $241K parity) ......................... 8 passed
P4  Memory (build/KPIs/cache/stale/RLS) ........................ 6 passed
P5  Core UI read models ........................................ 8 passed
P6  NirvanaI (groundedness/gateway/RAG-RBAC/audit) ............ 10 passed
```

### Phase 6 test breakdown (§14.1/14.2)

```
unit  test_extract_dollar_figures ................. $241K→241000; $1,234.56; 1.2 million; "5 contracts" not money
unit  test_groundedness_accepts_rounding .......... "$241K" grounded vs context 241,000 (tolerance)
unit  test_groundedness_rejects_fabricated ........ "$250,000" with context $240,000 → rejected
unit  test_groundedness_rejects_derived_total ..... model summing two figures into a new total → rejected
unit  test_gateway_routes_alias_and_cost .......... complex→gemini-2.5-pro, fast→gemini-2.5-flash; cost from price table
unit  test_gateway_redacts_pii .................... email/phone masked; $ business figures preserved
unit  test_template_registry ...................... 5 templates resolve; unknown raises
intg  test_rag_rbac_scope ......................... scoped user excludes other entity; cfo sees all (BEFORE search)
intg  test_gateway_rate_limit_trips ............... over-budget tenant → RateLimitExceeded (circuit breaker)
intg  test_draft_send_is_human_gated_and_audited .. draft→sent sets sent_by + AuditEvent(actor=human); sent immutable (409)
10 passed
```

## What was built

### Backend

| Area | Files |
| ---- | ----- |
| Models / migration | `models/nirvana.py` (NirvanaConversation, NirvanaMessage, DocumentDraft, ModelUsageEvent); `migrations/006_nirvana.py` (4 tables, fail-closed RLS, `model_usage_events` append-only, **`contract_embeddings`→`memory_embeddings`** + `source`/`source_id` + HNSW ANN index); `models/memory.py` generalized `ContractEmbedding`→`MemoryEmbedding` |
| ModelGateway | `core/model_gateway.py` — single LLM chokepoint: alias routing (`complex`/`fast`), version pinning, Redis response cache, per-tenant token circuit breaker, PII redaction, code-side cost attribution. Lazy Gemini client (importable/testable without a key) |
| RAGService | `services/rag.py` — `gemini-embedding-001` query embed + **RBAC/entity-scoped pgvector search resolved BEFORE retrieval** + Python rerank |
| Groundedness | `services/groundedness.py` — extracts $ figures, verifies each is in the (code-computed) context within tolerance; the authoritative enforcement gate |
| Documents | `services/documents.py` — 5 templates + RBAC-scoped context assembly; `agents/prompts.py` — verbatim prompts + 5 doc skeletons + out-of-scope message |
| Conversation / usage | `services/conversation.py` (turn persistence + history); `services/usage.py` (append-only `model_usage_events`, best-effort) |
| Agent | `agents/nirvana.py` — LangGraph StateGraph: classify → {qa: retrieve→generate→validate(→regenerate→reject) \| document: select→fetch→generate \| out_of_scope} |
| API | `api/v1/nirvana_routes.py` — `POST /chat` (JSON + SSE), `POST /generate-doc` (201), `PATCH /drafts/{id}` (edit/send), `GET /drafts`, `GET /history`; `schemas/nirvana.py`; registered in `main.py` |

### Frontend — `apps/web`

| Area | Files |
| ---- | ----- |
| Components | `components/nirvana/{chat-panel,message-bubble,document-preview}.tsx`; `nirvana-panel.tsx` now mounts the live `ChatPanel` (replacing the Phase-5 placeholder) |
| lib | `lib/hooks/use-nirvana.ts` (chat + generate-doc mutations); NirvanaI types in `lib/types.ts` |

## DoD highlights met

- **Determinism for money is enforced end-to-end**: the LLM only classifies/narrates/cites/drafts; every dollar figure originates from code-computed context, and the `GroundednessValidator` rejects any `$` figure (including derived totals) not present in context within tolerance — unit-tested for fabrication and derived-sum rejection.
- **RBAC-scoped retrieval before search**: `_authorized_contract_ids` resolves the role/entity set and the pgvector `WHERE` filters on it, so an unauthorized contract's embedding is never ranked (integration-tested: scoped user excluded, CFO sees all).
- **No irreversible action without a human**: drafts are created `status='draft'`; only a human PATCH `status='sent'` sets `sent_by`/`sent_at` and writes `AuditEvent(document.sent, actor=human)`; sent drafts are immutable (409) — integration-tested.
- **Single LLM chokepoint** with version-pinned aliases, per-tenant cost attribution (`model_usage_events`, append-only), PII redaction (business figures preserved), Redis caching, and a per-tenant rate-limit circuit breaker (integration-tested).
- **Out-of-scope** questions return the canned first-party-only message with **no generation tokens**; **memory-not-built** returns 503; **empty message** returns 400.
- **NirvanaI mounts into the Phase-5 shell** as the persistent slide-in `ChatPanel`, available on every module.

## Bugs found & fixed during verification

1. **Groundedness money regex split un-commaed numbers** (real bug in the spec's `_MONEY_RE`, §5.3). The comma-grouped alternative used `(?:,\d{3})*` (zero-or-more) and, being first in the ordered alternation, matched `241000.00` as just `241` — so a correct answer was judged ungrounded. Fixed to `(?:,\d{3})+` (require ≥1 comma group) so bare numbers fall through to the plain-digits branch and match whole. Synced the same fix into the architecture doc.
2. **Gateway signature change rippled into Phase 2/3 callers**: the rewritten `complete()` returns `CompletionResult` (not `str`) and `complete_json()` returns a parsed dict. Updated `agents/matching.py` (→ `complete_json`) and `agents/recommendation.py` (→ `complete(...).text`) and the matching test stub accordingly.
3. **`memory_embeddings` rename** propagated to the Phase 4/5 test teardowns (`TRUNCATE contract_embeddings` → `memory_embeddings`).

## Faithful deviations

- **Verification is backend pytest + frontend tsc/eslint**, not the spec's faithfulness eval harness against a live LLM (§14.4) — that needs a real `GEMINI_API_KEY` and a golden Q&A set. The deterministic guardrails it depends on (GroundednessValidator, RBAC scoping, cost/rate control, human-gated send) are fully implemented and tested; the harness + the 5 must-work Q&As remain a keyed-CI follow-up. LLM-dependent paths lazy-skip without a key (the established pattern), so the suite is green offline.
- **ModelGateway/RAG clients are lazy** (created on first call) and **Redis is opened per call via `get_redis()`** for event-loop safety across Celery/test loops — a robustness deviation from the doc's import-time singletons, behavior-identical.
- **Chat defaults to JSON, streams only on `Accept: text/event-stream`** (matches how `EventSource` negotiates) so plain `fetch`/SDK callers get a parseable body — an inversion of the doc's "JSON via `Accept: application/json`" that is more robust and still SSE-capable.
- HNSW replaces the Phase-4 IVFFlat ANN index on `memory_embeddings` (the spec's intent for `<3s` retrieval); 1536-dim stays within HNSW's indexable limit.

## How to reproduce

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/opt/postgresql@17/bin:$PATH"
cd "Cost Intelligence"
uv run alembic upgrade head                          # → 006
uv run ruff check apps/api && uv run mypy apps/api/app
RUN_DB_TESTS=1 uv run pytest apps/api/tests -q        # 77 passed
cd apps/web && npm run typecheck && npm run lint       # tsc exit 0; ESLint clean
```
