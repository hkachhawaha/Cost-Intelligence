"""Oracle Fusion connector (§4.2). Basic-auth (service account) against the Fusion REST
endpoints; raw rows are reshaped by `OracleMapper`."""

from __future__ import annotations

import httpx
import pandas as pd

from app.connectors.erp.base import ErpConnectorBase, ErpConnectorConfig
from app.connectors.erp.mappers import OracleMapper
from app.core.secrets import load_secret

_ENDPOINTS = {
    "invoices": "/fscmRestApi/resources/11.13.18.05/invoices",
    "spend_records": "/fscmRestApi/resources/11.13.18.05/payablesTransactions",
}


class OracleConnector(ErpConnectorBase):
    source_type = "oracle"

    def __init__(self, config: ErpConnectorConfig, tenant_id: str, source_id: str):
        super().__init__(config, tenant_id, source_id)
        self.config: ErpConnectorConfig = config
        self.mapper = OracleMapper()
        self._auth: tuple[str, str] | None = None

    async def authenticate(self) -> None:
        secret = load_secret(self.config.credentials_secret)
        if not secret or "username" not in secret:
            raise PermissionError("oracle source is not connected (no service account)")
        self._auth = (secret["username"], secret["password"])

    async def fetch_raw(self, dataset: str) -> pd.DataFrame:
        if self._auth is None:
            await self.authenticate()
        async with httpx.AsyncClient(timeout=60.0, auth=self._auth) as client:
            resp = await client.get(
                f"{self.config.base_url}{_ENDPOINTS[dataset]}",
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            payload = resp.json()
        rows = payload.get("items", payload) if isinstance(payload, dict) else payload
        df = pd.DataFrame(rows)
        return self.map_columns(df, dataset)
