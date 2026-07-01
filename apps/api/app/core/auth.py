"""Auth0 RS256 JWT validation with a JWKS cache.

Verifies bearer tokens against the Auth0 tenant's JWKS (RS256 only), validates
`aud`/`iss`/`exp`, and extracts the platform `Principal` from namespaced custom
claims (set by an Auth0 post-login Action). Binds the tenant to the request
context so DB sessions enforce RLS.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from app.core.config import settings
from app.core.tenancy import set_tenant

bearer_scheme = HTTPBearer(auto_error=False)

# Custom-claim namespace (configured in the Auth0 Action / Rule).
_NS = "https://terzo.ai"


@dataclass(frozen=True)
class Principal:
    user_id: str  # JWT `sub`
    tenant_id: str
    role: str | None
    entity_id: str | None
    email: str | None
    permissions: tuple[str, ...]


class _JWKSCache:
    """Caches Auth0 JWKS public keys; refreshes on TTL or unknown `kid`."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl = ttl_seconds
        self._keys: dict[str, dict] = {}
        self._fetched_at: float = 0.0

    async def get_key(self, kid: str) -> dict:
        if kid not in self._keys or (time.time() - self._fetched_at) > self._ttl:
            await self._refresh()
        if kid not in self._keys:
            # Unknown kid even after a TTL-driven refresh ⇒ force one more (rotation).
            await self._refresh()
        key = self._keys.get(kid)
        if key is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown signing key")
        return key

    async def _refresh(self) -> None:
        url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        self._keys = {k["kid"]: k for k in resp.json()["keys"]}
        self._fetched_at = time.time()


jwks_cache = _JWKSCache()


def _dev_bypass_active() -> bool:
    """Local-only auth bypass. Refused in production no matter the flag (defense in depth)."""
    return settings.dev_auth_bypass and not settings.is_production


def _dev_principal() -> Principal:
    """Fixed demo Principal for local end-to-end testing. Binds the demo tenant for RLS."""
    set_tenant(settings.dev_tenant_id)
    return Principal(
        user_id=settings.dev_user_id,
        tenant_id=settings.dev_tenant_id,
        role=settings.dev_role,
        entity_id=None,
        email="dev@terzo.local",
        permissions=("*",),
    )


async def get_current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    if _dev_bypass_active():
        return _dev_principal()
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = creds.credentials

    try:
        if settings.supabase_jwt_secret:
            # Decode using Supabase HS256
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            # Decode using Auth0 RS256
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not kid:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing kid")
            key = await jwks_cache.get_key(kid)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=settings.auth0_audience,
                issuer=settings.auth0_issuer,
            )
    except ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired") from exc
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}") from exc

    # Unpack claims: support both custom namespace and Supabase app_metadata
    app_metadata = claims.get("app_metadata", {})
    tenant_id = (
        app_metadata.get("tenant_id")
        or claims.get("tenant_id")
        or claims.get(f"{_NS}/tenant_id")
    )
    if not tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token missing tenant claim")

    # Bind tenant to the request context BEFORE any DB access in the handler.
    set_tenant(tenant_id)

    role = (
        app_metadata.get("role")
        or claims.get("role")
        or claims.get(f"{_NS}/role")
    )
    entity_id = (
        app_metadata.get("entity_id")
        or claims.get("entity_id")
        or claims.get(f"{_NS}/entity_id")
    )
    email = claims.get("email") or app_metadata.get("email")
    permissions = (
        app_metadata.get("permissions")
        or claims.get("permissions")
        or claims.get(f"{_NS}/permissions", [])
    )

    return Principal(
        user_id=claims["sub"],
        tenant_id=tenant_id,
        role=role,
        entity_id=entity_id,
        email=email,
        permissions=tuple(permissions),
    )
