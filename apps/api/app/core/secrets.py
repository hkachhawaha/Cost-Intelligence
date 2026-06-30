"""Secret store abstraction.

`store_secret`/`load_secret` persist small JSON secrets (e.g. an OAuth refresh
token) keyed by an opaque reference. The reference — never the value — is what
gets written to `data_sources.credentials_secret`.

Providers:
- `env`  (default, local/dev): file-backed JSON under `LOCAL_SECRETS_DIR` (git-ignored).
- `redis`: Redis-backed JSON store for dynamic secrets (e.g. on Railway/Vercel).
- `aws_sm` / `gcp_sm`: stubbed here; wire to the cloud manager in deployment.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import redis

from app.core.config import settings


def _local_path(ref: str) -> Path:
    base = Path(settings.local_secrets_dir)
    base.mkdir(parents=True, exist_ok=True)
    # ref is a filename-safe token; strip any path separators defensively.
    return base / f"{ref.replace('/', '_')}.json"


def store_secret(value: dict, *, ref: str | None = None) -> str:
    """Persist a secret; returns the reference to store on the record."""
    ref = ref or f"secret-{uuid4().hex}"
    if settings.secrets_provider == "env":
        _local_path(ref).write_text(json.dumps(value))
        return ref
    elif settings.secrets_provider == "redis":
        r = redis.from_url(str(settings.redis_url))
        r.set(f"secret:{ref}", json.dumps(value))
        return ref
    raise NotImplementedError(f"secrets_provider {settings.secrets_provider} not wired")


def load_secret(ref: str) -> dict | None:
    """Load a secret by reference, or None if absent."""
    if not ref:
        return None
    if settings.secrets_provider == "env":
        path = _local_path(ref)
        if not path.exists():
            return None
        return json.loads(path.read_text())
    elif settings.secrets_provider == "redis":
        r = redis.from_url(str(settings.redis_url))
        val = r.get(f"secret:{ref}")
        if not val:
            return None
        return json.loads(val)
    raise NotImplementedError(f"secrets_provider {settings.secrets_provider} not wired")
