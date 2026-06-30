"""Google Sheets OAuth connect + callback.

The callback validates the signed `state`, exchanges the code for tokens, stores
the refresh token in the secret store (only the ref lands on the DataSource),
and flips the source to `connected`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.connectors.oauth import exchange_code_for_tokens, verify_state
from app.core.config import settings
from app.core.database import session_for_tenant
from app.core.rbac import require_permission
from app.core.secrets import store_secret
from app.models.staging import DataSource

router = APIRouter(prefix="/google-sheets")


@router.get("/oauth/callback")
async def oauth_callback(code: str | None = None, state: str | None = None):
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing code/state")
    claims = verify_state(state)
    if claims is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or tampered state")

    tenant_id = claims["tenant_id"]
    source_id = claims["source_id"]
    tokens = await exchange_code_for_tokens(code)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no refresh_token returned")

    secret_ref = store_secret({"refresh_token": refresh_token})
    async with await session_for_tenant(tenant_id) as session:
        ds = await session.get(DataSource, UUID(source_id))
        if ds is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "data source not found")
        ds.credentials_secret = secret_ref
        ds.status = "connected"
        await session.commit()

    return RedirectResponse(
        url=f"{settings.google_oauth_redirect_uri.split('/api/')[0]}"
        "/settings/data-sources?connected=1"
    )


@router.get("/oauth/start", dependencies=[Depends(require_permission("admin"))])
async def oauth_start(source_id: UUID):
    # Convenience: the create endpoint already returns the consent URL; this
    # re-issues one for an existing source.
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED, "use the oauth_url from POST /data-sources"
    )
