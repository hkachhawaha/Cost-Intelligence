"""Phase 9 integration (§5.1, §5.2, §9) — live Postgres, migration 009.

The gated-automation guarantee end-to-end: a high-confidence, time-sensitive opportunity
produces a task that WAITS at `awaiting_approval`; only a human approve fires the external
action (audited), a reject sends nothing, the executor refuses an unapproved gate, and a
re-decision is a 409. Plus the learning loop's sparse-data skip. No LLM key needed.

Run: RUN_DB_TESTS=1 uv run pytest apps/api/tests/integration/test_workflow_pipeline.py -v
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requires_db

pytestmark = requires_db

_TRUNCATE = (
    "TRUNCATE tenants, users, vendors, opportunities, tasks, approval_gates, "
    "task_reminders, connector_credentials, learning_labels, model_calibration, "
    "agent_runs, audit_events CASCADE"
)


def _dsn() -> str:
    from app.core.config import settings

    return settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")


def _admin():
    import psycopg

    return psycopg.connect(_dsn(), autocommit=True)


@pytest.fixture()
def tenant():
    tid = str(uuid.uuid4())
    yield tid
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(_TRUNCATE)
    admin.close()


def _client(tenant: str, user_id: str, role: str, monkeypatch) -> TestClient:
    from app.core import auth as auth_mod
    from app.core.auth import Principal, get_current_principal
    from app.core.database import get_session, session_for_tenant
    from app.main import app

    async def _noop():
        return None

    monkeypatch.setattr(auth_mod.jwks_cache, "_refresh", _noop)

    async def _principal() -> Principal:
        return Principal(
            user_id=user_id, tenant_id=tenant, role=role, entity_id=None,
            email="u@acme.com", permissions=("*",),
        )

    async def _session():
        s = await session_for_tenant(tenant)
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise
        finally:
            await s.close()

    app.dependency_overrides[get_current_principal] = _principal
    app.dependency_overrides[get_session] = _session
    return TestClient(app)


async def _seed_tenant_user(tenant: str, user_id: str) -> None:
    from app.core.database import session_for_tenant
    from app.models.tenant import Tenant
    from app.models.user import User

    tid = uuid.UUID(tenant)
    async with await session_for_tenant(tenant) as s:
        s.add(Tenant(id=tid, name="Acme", slug=f"acme{tenant[:8]}", encryption_key_ref="kms://t"))
        await s.flush()
        s.add(User(id=uuid.UUID(user_id), tenant_id=tid, auth0_id=f"a|{user_id[:8]}",
                   email="owner@acme.com"))
        await s.commit()


async def _seed_opportunity(tenant: str, owner_id: str, *, otype="auto_renewal",
                            confidence="0.95") -> str:
    from app.core.database import session_for_tenant
    from app.models.opportunity import Opportunity

    oid = uuid.uuid4()
    async with await session_for_tenant(tenant) as s:
        s.add(Opportunity(
            id=oid, tenant_id=uuid.UUID(tenant), type=otype, bucket="savings",
            impact=Decimal("50000"), confidence=Decimal(confidence),
            owner_id=uuid.UUID(owner_id), status="detected",
        ))
        await s.commit()
    return str(oid)


async def _run_workflow(tenant: str, opp_id: str, *, confidence=0.95,
                        deadline="2026-09-01") -> dict:
    from app.core.database import session_for_tenant
    from app.services.workflow import WorkflowService

    async with await session_for_tenant(tenant) as s:
        out = await WorkflowService(s, tenant).run_for_opportunity(
            opportunity_id=opp_id, opportunity_type="auto_renewal",
            confidence=confidence, deadline=deadline,
        )
        await s.commit()
    return out


def _audit_events(tenant: str, event_type: str) -> int:
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM audit_events WHERE tenant_id=%s AND event_type=%s",
            (tenant, event_type),
        )
        n = cur.fetchone()[0]
    admin.close()
    return n


# ── positive: full gated approve flow → external action fires + is audited ────────
def test_gated_approve_flow_executes_external_action(tenant, monkeypatch):
    user_id = str(uuid.uuid4())
    asyncio.run(_seed_tenant_user(tenant, user_id))
    opp_id = asyncio.run(_seed_opportunity(tenant, user_id))
    out = asyncio.run(_run_workflow(tenant, opp_id))
    assert out["skipped"] is False
    task_id = out["task_id"]

    # Task waits at awaiting_approval — nothing sent yet.
    assert _audit_events(tenant, "external_action.executed") == 0

    client = _client(tenant, user_id, "cfo", monkeypatch)
    try:
        body = client.get(f"/api/v1/tasks/{task_id}").json()
        assert body["status"] == "awaiting_approval"
        assert body["pending_gate_id"] is not None

        r = client.post(f"/api/v1/tasks/{task_id}/approve", json={"note": "ok to send"})
        assert r.status_code == 200
        assert r.json()["status"] == "completed"
        assert r.json()["external_result"]["status"] == "sent"
        # NOW the external action is recorded exactly once.
        assert _audit_events(tenant, "external_action.executed") == 1
    finally:
        from app.main import app

        app.dependency_overrides.clear()


# ── negative: reject sends nothing ────────────────────────────────────────────────
def test_reject_sends_nothing(tenant, monkeypatch):
    user_id = str(uuid.uuid4())
    asyncio.run(_seed_tenant_user(tenant, user_id))
    opp_id = asyncio.run(_seed_opportunity(tenant, user_id))
    task_id = asyncio.run(_run_workflow(tenant, opp_id))["task_id"]

    client = _client(tenant, user_id, "legal", monkeypatch)
    try:
        r = client.post(f"/api/v1/tasks/{task_id}/reject", json={"note": "do not send"})
        assert r.status_code == 200 and r.json()["status"] == "cancelled"
        assert _audit_events(tenant, "external_action.executed") == 0  # never sent
        assert _audit_events(tenant, "approval.decided") == 1
    finally:
        from app.main import app

        app.dependency_overrides.clear()


# ── error/idempotency: a completed task cannot be re-approved (no second send) ────
def test_cannot_reapprove_completed_task(tenant, monkeypatch):
    user_id = str(uuid.uuid4())
    asyncio.run(_seed_tenant_user(tenant, user_id))
    opp_id = asyncio.run(_seed_opportunity(tenant, user_id))
    task_id = asyncio.run(_run_workflow(tenant, opp_id))["task_id"]

    client = _client(tenant, user_id, "cfo", monkeypatch)
    try:
        assert client.post(f"/api/v1/tasks/{task_id}/approve", json={}).status_code == 200
        # No pending gate remains → re-approve is rejected (404), and nothing fires twice.
        assert client.post(f"/api/v1/tasks/{task_id}/approve", json={}).status_code == 404
        assert _audit_events(tenant, "external_action.executed") == 1  # exactly once
    finally:
        from app.main import app

        app.dependency_overrides.clear()


# ── error: deciding an already-decided gate at the service layer → 409 ────────────
def test_record_decision_on_decided_gate_conflicts(tenant):
    from app.core.database import session_for_tenant
    from app.services.task import GateAlreadyDecided, TaskService

    user_id = str(uuid.uuid4())
    asyncio.run(_seed_tenant_user(tenant, user_id))

    async def _decide_twice() -> bool:
        async with await session_for_tenant(tenant) as s:
            svc = TaskService(s, tenant)
            task = await svc.create(opportunity_id=None, type="review", title="t")
            gate = await svc.open_approval_gate(
                str(task.id), action_type="external_send", action_payload={}
            )
            await svc.record_decision(str(gate.id), approved=True, decided_by=user_id)
            try:
                await svc.record_decision(str(gate.id), approved=False, decided_by=user_id)
                return False
            except GateAlreadyDecided:
                return True

    assert asyncio.run(_decide_twice()) is True


# ── error: non-approver role cannot approve (403) ─────────────────────────────────
def test_non_approver_role_forbidden(tenant, monkeypatch):
    user_id = str(uuid.uuid4())
    asyncio.run(_seed_tenant_user(tenant, user_id))
    opp_id = asyncio.run(_seed_opportunity(tenant, user_id))
    task_id = asyncio.run(_run_workflow(tenant, opp_id))["task_id"]

    client = _client(tenant, user_id, "analyst", monkeypatch)  # not in approve_roles
    try:
        assert client.post(f"/api/v1/tasks/{task_id}/approve", json={}).status_code == 403
        assert _audit_events(tenant, "external_action.executed") == 0
    finally:
        from app.main import app

        app.dependency_overrides.clear()


# ── defense in depth: executor refuses an unapproved gate ─────────────────────────
def test_executor_refuses_unapproved_gate(tenant, monkeypatch):
    from app.core.database import session_for_tenant
    from app.services.external_actions import ExternalActionExecutor, UnapprovedActionError
    from app.services.task import TaskService

    user_id = str(uuid.uuid4())
    asyncio.run(_seed_tenant_user(tenant, user_id))
    opp_id = asyncio.run(_seed_opportunity(tenant, user_id))

    async def _attempt() -> bool:
        async with await session_for_tenant(tenant) as s:
            svc = TaskService(s, tenant)
            task = await svc.create(opportunity_id=opp_id, type="non_renewal", title="t")
            gate = await svc.open_approval_gate(
                str(task.id), action_type="external_send", action_payload={"document_id": None}
            )  # gate stays 'pending' — never approved
            await s.flush()
            try:
                await ExternalActionExecutor(s, tenant).send_document(
                    document_id=None, approval_gate_id=str(gate.id)
                )
                return False
            except UnapprovedActionError:
                return True

    assert asyncio.run(_attempt()) is True


# ── error: illegal task status transition → 409 ───────────────────────────────────
def test_illegal_status_transition_conflicts(tenant, monkeypatch):
    from app.core.database import session_for_tenant
    from app.services.task import TaskService

    user_id = str(uuid.uuid4())
    asyncio.run(_seed_tenant_user(tenant, user_id))

    async def _make() -> str:
        async with await session_for_tenant(tenant) as s:
            task = await TaskService(s, tenant).create(
                opportunity_id=None, type="review", title="t"
            )
            await s.commit()
            return str(task.id)

    task_id = asyncio.run(_make())
    client = _client(tenant, user_id, "cfo", monkeypatch)
    try:
        # open → completed is not a legal transition (must go through in_progress).
        r = client.patch(f"/api/v1/tasks/{task_id}/status", json={"status": "completed"})
        assert r.status_code == 409
    finally:
        from app.main import app

        app.dependency_overrides.clear()


# ── edge: learning recalibration skips on sparse data ─────────────────────────────
def test_recalibration_skips_when_sparse(tenant):
    from app.core.database import session_for_tenant
    from app.services.feedback_loop import LearningFeedbackService

    user_id = str(uuid.uuid4())
    asyncio.run(_seed_tenant_user(tenant, user_id))

    async def _recal() -> dict:
        async with await session_for_tenant(tenant) as s:
            svc = LearningFeedbackService(s, tenant)
            # Capture a handful of signals — far below the configured floors.
            for _ in range(3):
                await svc.on_match_confirmed(uuid.uuid4(), {"vendor": 0.9, "correct": True},
                                             uuid.uuid4())
            out = await svc.recalibrate_all()
            await s.commit()
            return out

    result = asyncio.run(_recal())
    # Both targets skip (return None) below their example floors — sparse-safe.
    assert result["fuzzy_weights"] is None
    assert result["detection_thresholds"] is None
