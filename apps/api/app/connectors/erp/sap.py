"""SAP connector (§4.2). OData v2 with an API key (S/4HANA Cloud / Ariba); raw rows are
reshaped by `SapMapper`."""

from __future__ import annotations

import httpx
import pandas as pd

from app.connectors.erp.base import ErpConnectorBase, ErpConnectorConfig
from app.connectors.erp.mappers import SapMapper
from app.core.secrets import load_secret

_ENDPOINTS = {
    "invoices": "/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice",
    "spend_records": "/sap/opu/odata/sap/API_JOURNALENTRYITEMBASIC_SRV/A_JournalEntryItemBasic",
}


class SapConnector(ErpConnectorBase):
    source_type = "sap"

    def __init__(self, config: ErpConnectorConfig, tenant_id: str, source_id: str):
        super().__init__(config, tenant_id, source_id)
        self.config: ErpConnectorConfig = config
        self.mapper = SapMapper()
        self._api_key: str | None = None

    async def authenticate(self) -> None:
        secret = load_secret(self.config.credentials_secret)
        if not secret or "api_key" not in secret:
            raise PermissionError("sap source is not connected (no api key)")
        self._api_key = secret["api_key"]

    async def fetch_raw(self, dataset: str) -> pd.DataFrame:
        if self._api_key is None:
            await self.authenticate()
        assert self._api_key is not None  # authenticate() set it or raised
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.config.base_url}{_ENDPOINTS[dataset]}",
                headers={"APIKey": self._api_key, "Accept": "application/json"},
                params={"$format": "json"},
            )
            resp.raise_for_status()
            payload = resp.json()
        # OData v2 nests rows under d.results.
        rows = payload.get("d", {}).get("results", []) if isinstance(payload, dict) else payload
        df = pd.DataFrame(rows)
        return self.map_columns(df, dataset)
