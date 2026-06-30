"""Google OAuth2 (authorization-code) helpers + signed `state`.

`state` is an HMAC-signed token carrying tenant_id + source_id + a nonce so the
callback can validate the round-trip and bind the right source (anti-CSRF).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from urllib.parse import urlencode

import httpx

from app.core.config import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"


def sign_state(tenant_id: str, source_id: str, nonce: str) -> str:
    body = {"tenant_id": tenant_id, "source_id": source_id, "nonce": nonce}
    raw = json.dumps(body, sort_keys=True).encode()
    sig = hmac.new(settings.oauth_state_secret.encode(), raw, hashlib.sha256).digest()
    return urlsafe_b64encode(raw).decode() + "." + urlsafe_b64encode(sig).decode()


def verify_state(state: str) -> dict | None:
    try:
        raw_b64, sig_b64 = state.split(".", 1)
        raw = urlsafe_b64decode(raw_b64)
        sig = urlsafe_b64decode(sig_b64)
    except (ValueError, Exception):  # noqa: BLE001
        return None
    expected = hmac.new(settings.oauth_state_secret.encode(), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    return json.loads(raw)


def build_consent_url(state: str) -> str:
    """Authorization-code flow with offline access → receive a refresh token."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": SHEETS_SCOPE,
        "access_type": "offline",
        "prompt": "consent",  # force a refresh_token even on re-consent
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()
