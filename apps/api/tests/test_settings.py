"""Unit tests for typed settings (no DB)."""

from __future__ import annotations

from app.core.config import Settings

_BASE = dict(
    database_url="postgresql+asyncpg://u:p@localhost:5432/db",
    redis_url="redis://localhost:6379/0",
    auth0_domain="acme.us.auth0.com",
    auth0_audience="https://api.terzo.ai",
    auth0_client_id="cid",
    auth0_client_secret="secret",
)


def test_settings_defaults():
    # Note: `environment` is intentionally NOT asserted here — the test process
    # may set ENVIRONMENT in the ambient env, which (correctly) overrides the
    # field default. Assert the genuinely-defaulted fields instead.
    s = Settings(**_BASE)
    assert s.database_pool_size == 10
    assert s.database_max_overflow == 20
    assert s.secrets_provider == "env"
    assert s.is_production is False


def test_issuer_derives_from_domain():
    s = Settings(**_BASE)
    assert s.auth0_issuer == "https://acme.us.auth0.com/"


def test_explicit_issuer_overrides():
    s = Settings(**_BASE, auth0_issuer="https://custom/")
    assert s.auth0_issuer == "https://custom/"


def test_database_url_sync_uses_psycopg():
    s = Settings(**_BASE)
    assert "+psycopg" in s.database_url_sync
    assert "+asyncpg" not in s.database_url_sync


def test_is_production_true_for_prod():
    s = Settings(**_BASE, environment="prod")
    assert s.is_production is True


def test_secrets_provider_redis():
    s = Settings(**_BASE, secrets_provider="redis")
    assert s.secrets_provider == "redis"
