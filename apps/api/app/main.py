"""FastAPI application entrypoint.

Lifespan: configure logging, OTel, prefetch Auth0 JWKS, dispose the DB pool on
shutdown. Middleware: request-id assignment + per-request tenant reset (fail
closed), then CORS. Routers: health, me, auth-sync.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1 import (
    admin_routes,
    agent_runs_routes,
    anomalies_routes,
    auth_routes,
    commitment_routes,
    contracts_routes,
    cost_intelligence_routes,
    dashboard_routes,
    data_quality_routes,
    data_sources_routes,
    data_steward_routes,
    extraction_routes,
    google_sheets_routes,
    health_routes,
    indexation_routes,
    learning_routes,
    line_items_routes,
    match_results_routes,
    me_routes,
    nirvana_routes,
    opportunities_routes,
    portfolio_routes,
    rate_cards_routes,
    recovery_routes,
    renewals_routes,
    spend_routes,
    staging_routes,
    sync_routes,
    tasks_routes,
    vendors_routes,
)
from app.core.auth import jwks_cache
from app.core.config import settings
from app.core.database import engine
from app.core.logging import configure_logging
from app.core.otel import setup_otel
from app.core.tenancy import current_request_id, set_tenant

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    setup_otel(app)
    try:
        await jwks_cache._refresh()  # prefetch Auth0 keys
    except Exception:  # noqa: BLE001
        # Don't block startup if Auth0 is briefly unreachable; keys load on first use.
        log.warning("auth.jwks_prefetch_failed")
    if settings.dev_auth_bypass and not settings.is_production:
        log.warning(
            "api.dev_auth_bypass_ENABLED — Auth0 is BYPASSED; every request runs as the demo "
            "principal. Local testing only; never enable in production.",
            tenant_id=settings.dev_tenant_id,
        )
    log.info("api.startup", environment=settings.environment)
    yield
    await engine.dispose()
    log.info("api.shutdown")


app = FastAPI(
    title="Terzo Cost Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
    root_path=settings.api_root_path,
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, binds it to logging context, resets tenant per request."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id", str(uuid.uuid4()))
        current_request_id.set(rid)
        set_tenant(None)  # fail-closed default each request
        structlog.contextvars.bind_contextvars(request_id=rid, path=request.url.path)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["x-request-id"] = rid
        return response


app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_routes.router, tags=["health"])
app.include_router(me_routes.router, prefix="/api/v1", tags=["me"])
app.include_router(auth_routes.router, prefix="/api/v1", tags=["auth"])
app.include_router(data_sources_routes.router, prefix="/api/v1", tags=["data-sources"])
app.include_router(staging_routes.router, prefix="/api/v1", tags=["data-quality"])
app.include_router(google_sheets_routes.router, prefix="/api/v1", tags=["google-sheets"])
app.include_router(match_results_routes.router, prefix="/api/v1", tags=["matching"])
app.include_router(opportunities_routes.router, prefix="/api/v1", tags=["detection"])
app.include_router(opportunities_routes.detection_router, prefix="/api/v1", tags=["detection"])
app.include_router(sync_routes.router, prefix="/api/v1", tags=["sync"])
app.include_router(agent_runs_routes.router, prefix="/api/v1", tags=["audit"])
# Phase 5 — read-model endpoints (UI reads from memory; never from source)
app.include_router(dashboard_routes.router, prefix="/api/v1", tags=["dashboard"])
app.include_router(spend_routes.router, prefix="/api/v1", tags=["spend"])
app.include_router(contracts_routes.router, prefix="/api/v1", tags=["contracts"])
app.include_router(renewals_routes.router, prefix="/api/v1", tags=["renewals"])
app.include_router(recovery_routes.router, prefix="/api/v1", tags=["recovery"])
app.include_router(data_quality_routes.router, prefix="/api/v1", tags=["data-quality"])
# Phase 6 — NirvanaI conversational assistant
app.include_router(nirvana_routes.router, prefix="/api/v1", tags=["nirvana"])
# Phase 7 — Advanced modules & agents
app.include_router(vendors_routes.router, prefix="/api/v1", tags=["vendors"])
app.include_router(indexation_routes.router, prefix="/api/v1", tags=["indexation"])
app.include_router(portfolio_routes.router, prefix="/api/v1", tags=["portfolio"])
app.include_router(extraction_routes.router, prefix="/api/v1", tags=["extraction"])
app.include_router(anomalies_routes.router, prefix="/api/v1", tags=["anomalies"])
app.include_router(data_steward_routes.router, prefix="/api/v1", tags=["data-steward"])
# Phase 8 — line-item depth & recovery
app.include_router(rate_cards_routes.router, prefix="/api/v1", tags=["rate-cards"])
app.include_router(line_items_routes.router, prefix="/api/v1", tags=["line-items"])
# Phase 9 — agentic automation & continuous learning
app.include_router(tasks_routes.router, prefix="/api/v1", tags=["tasks"])
app.include_router(learning_routes.router, prefix="/api/v1", tags=["learning"])
# Phase 10 — control layer & portfolio governance (portfolio_routes already registered in P7;
# its new governance endpoints ship on the same router)
app.include_router(commitment_routes.router, prefix="/api/v1", tags=["commitment"])
app.include_router(admin_routes.router, prefix="/api/v1", tags=["admin"])
# Realignment — Cost Intelligence (single-workspace, Google-Sheets-driven)
app.include_router(cost_intelligence_routes.router, prefix="/api/v1", tags=["cost-intelligence"])
