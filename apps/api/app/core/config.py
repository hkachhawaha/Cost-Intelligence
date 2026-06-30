"""Typed application configuration.

A single `Settings` object loaded from environment (or a local `.env` in dev)
via pydantic-settings. This is the ONLY place environment variables are read —
never touch os.environ elsewhere.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- App ---
    environment: str = Field(default="local")  # local|dev|staging|prod
    log_level: str = Field(default="INFO")
    api_root_path: str = Field(default="")
    cors_allowed_origins: str = Field(default="http://localhost:3000")  # comma-separated list of allowed CORS origins

    # --- Local dev auth bypass (NEVER active in prod; for local end-to-end testing) ---
    # When true AND environment != prod, get_current_principal returns a fixed demo
    # Principal instead of validating an Auth0 JWT. Pairs with the seed script + the
    # frontend NEXT_PUBLIC_DEV_AUTH flag. Platform-refused in production.
    dev_auth_bypass: bool = Field(default=False)
    dev_tenant_id: str = Field(default="000000d0-0000-4000-8000-000000000000")
    dev_user_id: str = Field(default="000000d1-0000-4000-8000-000000000000")
    dev_role: str = Field(default="admin")

    # --- Datastores ---
    database_url: PostgresDsn  # postgresql+asyncpg://...
    database_pool_size: int = Field(default=10)
    database_max_overflow: int = Field(default=20)
    redis_url: RedisDsn
    clickhouse_url: str | None = None

    # --- Auth0 ---
    auth0_domain: str
    auth0_audience: str
    auth0_client_id: str
    auth0_client_secret: str
    auth0_issuer: str | None = None  # defaults to https://{domain}/

    # --- Object store / secrets ---
    s3_bucket: str | None = None
    aws_region: str = "us-east-1"
    secrets_provider: str = "env"  # env|aws_sm|gcp_sm|redis
    local_secrets_dir: str = ".secrets"  # file-backed secret store for local/dev

    # --- Ingestion / Google Sheets (Phase 1) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/api/v1/google-sheets/oauth/callback"
    oauth_state_secret: str = "dev-oauth-state-secret-change-me"
    ingestion_fetch_chunk_rows: int = 50000
    ingestion_upsert_chunk: int = 5000
    vendor_dedup_threshold: float = 0.92

    # --- LLM (Google Gemini; used from Phase 6, declared early for parity) ---
    # One key for both generation (model gateway) and embeddings (Gemini Developer API).
    gemini_api_key: str | None = None

    # --- Memory layer (Phase 4) ---
    memory_cache_ttl_seconds: int = 86_400  # Redis KPI cache safety-net TTL
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 1536  # gemini-embedding-001 MRL output; ≤2000 so ivfflat can index it
    embedding_batch_size: int = 128
    embedding_fatal_to_sync: bool = False  # embed failure → partial sync, not failed
    ivfflat_lists: int = 100
    agent_run_stuck_minutes: int = 30
    snapshot_kms: bool = True

    # --- NirvanaI / ModelGateway (Phase 6) ---
    model_tokens_per_minute_per_tenant: int = 120_000  # gateway circuit breaker
    model_cache_ttl_s: int = 900  # gateway response-cache TTL
    nirvana_rag_top_k: int = 8  # chunks fed to generation
    nirvana_rag_overscan: int = 4  # candidate multiplier before rerank (k × overscan)
    nirvana_history_turns: int = 8  # prior turns included in the prompt
    nirvana_groundedness_rel_tol: float = 0.005  # rounding tolerance for $ grounding
    nirvana_enable_llm_groundedness_check: bool = False  # optional secondary LLM check

    # --- Advanced modules & agents (Phase 7) ---
    anomaly_zscore_threshold: float = 3.0  # spend-spike sensitivity
    anomaly_iqr_multiplier: float = 1.5  # off-pattern GL sensitivity
    anomaly_dup_window_days: int = 7  # duplicate-payment window
    consolidation_min_vendors: int = 3  # candidate threshold
    consolidation_min_category_spend: int = 50_000  # candidate threshold ($)
    tenant_base_currency: str = "USD"  # FX normalization target (per-tenant overridable)
    extraction_verify_roles: tuple[str, ...] = ("legal", "admin")  # roles allowed to verify
    taxonomy_low_confidence: float = 0.7  # below → routed to HITL spot-check

    # --- Line-item depth & recovery (Phase 8) ---
    above_rate_min_delta_usd: Decimal = Decimal("50")  # ignore trivial overcharges
    volume_tier_min_savings_usd: Decimal = Decimal("100")
    rate_card_auto_verify_threshold: Decimal = Decimal(
        "0.97"
    )  # ≥ → propose auto-verify (still HITL)
    sku_normalization_threshold: float = 0.85
    line_item_detection_enabled: bool = True  # per-tenant override via tenants.autonomy_config
    rate_card_verify_roles: tuple[str, ...] = ("legal", "category_mgr", "admin")

    # --- Agentic automation & connectors (Phase 9) ---
    workflow_min_confidence: float = 0.90  # gate: only high-confidence opps automate
    workflow_auto_types: tuple[str, ...] = ("auto_renewal", "uplift_creep")
    workflow_reminder_lead_days: int = 7
    workflow_approval_required: bool = True  # PLATFORM-enforced — never disabled
    workflow_approve_roles: tuple[str, ...] = ("category_mgr", "legal", "admin", "cfo")
    learning_min_examples_fuzzy: int = 200
    learning_min_examples_thresholds: int = 100
    detection_threshold_min: float = 0.0
    detection_threshold_max: float = 1_000_000.0
    anomaly_if_contamination: float = 0.02
    anomaly_if_window_days: int = 90
    event_bus_mode: str = "redis"  # redis|dual|kafka
    kafka_bootstrap_servers: str = ""

    # --- Commitment Check & portfolio governance (Phase 10) ---
    commitment_scenario_moves: tuple[int, ...] = (5, 10, 15)
    commitment_required_roles: tuple[str, ...] = ("cfo", "portfolio_admin", "legal", "admin")
    # External-intelligence seam — PERMANENTLY OFF in v1–v3 (platform-enforced; §3.4).
    external_intelligence_enabled: bool = False
    # Scalability / tiering.
    spend_hot_retain_months: int = 12  # hot in Postgres
    spend_warm_retain_months: int = 60  # warm in ClickHouse
    partition_ahead_months: int = 3
    clickhouse_query_timeout_s: int = 10
    # Per-tenant quotas / circuit breakers.
    default_max_spend_rows: int = 10_000_000
    default_max_llm_tokens_day: int = 5_000_000
    default_max_query_qps: int = 50
    breaker_failure_threshold: int = 3
    breaker_reset_seconds: int = 30
    # NFR targets (asserted in load tests).
    nfr_dashboard_ms: int = 5000
    nfr_query_ms: int = 3000
    nfr_uptime_pct: float = 99.9

    # --- Cost Intelligence data source (Google Sheets, single workspace) ---
    # The connected workbook is read via the PUBLIC xlsx/csv export (no OAuth) — the sheet
    # must be shared "anyone with the link can view". Default = the Nexus demo workbook.
    ci_default_spreadsheet_url: str = (
        "https://docs.google.com/spreadsheets/d/"
        "1DiOWK243sZaIXOw6ZTYnt3aGLnuZ9DYT0ITQOsWXwxg/edit"
    )
    ci_sheet_fetch_timeout_s: int = 60
    # Insight assumptions (mirror the prototype's tunable thresholds).
    ci_recapture_rate: float = 0.10  # maverick recapture
    ci_unused_pct: float = 0.15  # unused-commitment threshold
    ci_overspend_pct: float = 0.05  # overspend-vs-ACV threshold
    ci_renewal_lookahead_days: int = 90
    ci_renewal_uplift_pct: float = 0.05  # assumed renewal uplift (first-party assumption)
    ci_shelfware_min_idle_pct: float = 0.20  # licensed-but-inactive share to flag
    ci_as_of_date: str = ""  # override "today" for deterministic insights (blank = real today)

    # --- Observability ---
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "terzo-api"

    @field_validator("auth0_issuer", mode="before")
    @classmethod
    def _default_issuer(cls, v, info):
        if v:
            return v
        domain = info.data.get("auth0_domain")
        return f"https://{domain}/" if domain else None

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"

    @property
    def database_url_sync(self) -> str:
        """Synchronous DSN for Alembic (asyncpg → psycopg)."""
        return str(self.database_url).replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
