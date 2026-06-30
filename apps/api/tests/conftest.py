"""Shared test fixtures and environment defaults.

Sets required env vars BEFORE `app.core.config` is imported anywhere. Unit/API
tests need no database; integration tests (RLS isolation, migration, audit
immutability) require a live Postgres and run only when RUN_DB_TESTS=1.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://terzo:dev@localhost:5432/terzo")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AUTH0_DOMAIN", "test.us.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.terzo.ai")
os.environ.setdefault("AUTH0_CLIENT_ID", "test")
os.environ.setdefault("AUTH0_CLIENT_SECRET", "test")

import pytest

RUN_DB_TESTS = os.environ.get("RUN_DB_TESTS") == "1"

requires_db = pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="RUN_DB_TESTS!=1 (needs a live Postgres with migration 001 applied)",
)
