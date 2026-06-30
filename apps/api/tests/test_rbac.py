"""Unit tests for RBAC permission enforcement (no DB)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.auth import Principal
from app.core.rbac import require_permission


def _principal(*perms: str) -> Principal:
    return Principal(
        user_id="auth0|1",
        tenant_id="t1",
        role="cfo",
        entity_id=None,
        email="a@b.com",
        permissions=tuple(perms),
    )


async def test_admin_wildcard_passes_all():
    dep = require_permission("contract:write")
    out = await dep(principal=_principal("*"))
    assert out.permissions == ("*",)


async def test_exact_permission_passes():
    dep = require_permission("contract:read")
    out = await dep(principal=_principal("contract:read", "spend:read"))
    assert out is not None


async def test_missing_permission_denied():
    dep = require_permission("contract:write")
    with pytest.raises(HTTPException) as exc:
        await dep(principal=_principal("contract:read"))
    assert exc.value.status_code == 403
