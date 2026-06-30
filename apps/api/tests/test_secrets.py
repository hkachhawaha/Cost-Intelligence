from __future__ import annotations

import pytest
from app.core.config import settings
from app.core.secrets import store_secret, load_secret


def test_env_secrets_lifecycle(monkeypatch, tmp_path):
    # Set secrets provider to env and point local_secrets_dir to temporary path
    monkeypatch.setattr(settings, "secrets_provider", "env")
    monkeypatch.setattr(settings, "local_secrets_dir", str(tmp_path))

    secret_data = {"token": "test-token-value"}
    ref = store_secret(secret_data)
    assert ref.startswith("secret-")

    loaded = load_secret(ref)
    assert loaded == secret_data


def test_redis_secrets_lifecycle(monkeypatch):
    # Set secrets provider to redis
    monkeypatch.setattr(settings, "secrets_provider", "redis")

    secret_data = {"api_key": "redis-test-key"}
    ref = store_secret(secret_data)
    assert ref.startswith("secret-")

    loaded = load_secret(ref)
    assert loaded == secret_data
