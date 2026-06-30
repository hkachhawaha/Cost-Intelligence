"""RBAC permission enforcement.

`require_permission` is a dependency factory. Permissions are carried in the JWT
(`https://terzo.ai/permissions`) and mirror the role seed in Migration 001.
Admin holds the wildcard `*` and passes every check.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status

from app.core.auth import Principal, get_current_principal

ALL = "*"


def require_permission(permission: str) -> Callable[..., Awaitable[Principal]]:
    """Usage:
    @router.get(..., dependencies=[Depends(require_permission('contract:read'))])
    """

    async def _dep(principal: Principal = Depends(get_current_principal)) -> Principal:
        perms = set(principal.permissions)
        if ALL in perms or permission in perms:
            return principal
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"missing permission: {permission}",
        )

    return _dep
