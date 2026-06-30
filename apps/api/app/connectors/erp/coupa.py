"""Coupa connector (§4.2). OAuth2 client-credentials against the Coupa REST API; raw rows
are reshaped by `CoupaMapper`. Secrets are loaded by ref — never stored in the connector."""

from __future__ import annotations

import httpx
import pandas as pd

from app.connectors.erp.base import ErpConnectorBase, ErpConnectorConfig
from app.connectors.erp.mappers import CoupaMapper
from app.core.secrets import load_secret

_ENDPOINTS = {"invoices": "/api/invoices", "spend_records": "/api/expense_lines"}


class CoupaConnector(ErpConnectorBase):
    source_type = "coupa"

    def __init__(self, config: ErpConnectorConfig, tenant_id: str, source_id: str):
        super().__init__(config, tenant_id, source_id)
        self.config: ErpConnectorConfig = config
        self.mapper = CoupaMapper()
        self._token: str | None = None

    async def authenticate(self) -> None:
        secret = load_secret(self.config.credentials_secret)
        if not secret or "client_id" not in secret:
            raise PermissionError("coupa source is not connected (no client credentials)")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.config.base_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": secret["client_id"],
                    "client_secret": secret["client_secret"],
                    "scope": secret.get("scope", "core.invoice.read core.expense.read"),
                },
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]

    async def fetch_raw(self, dataset: str) -> pd.DataFrame:
        if self._token is None:
            await self.authenticate()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.config.base_url}{_ENDPOINTS[dataset]}",
                headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
            )
            resp.raise_for_status()
            rows = resp.json()
        df = pd.DataFrame(rows if isinstance(rows, list) else rows.get("data", []))
        return self.map_columns(df, dataset)
