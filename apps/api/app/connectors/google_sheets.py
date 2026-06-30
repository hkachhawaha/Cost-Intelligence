"""Google Sheets connector — reads the three dataset tabs via Sheets API v4."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import pandas as pd

from app.connectors.base import ConnectorBase, ConnectorConfig
from app.connectors.oauth import refresh_access_token
from app.core.secrets import load_secret

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


@dataclass
class GoogleSheetsConfig(ConnectorConfig):
    spreadsheet_id: str = ""
    ranges: dict[str, str] = field(
        default_factory=lambda: {
            "contracts": "Contracts!A1:CZ100000",
            "spend_records": "Spend!A1:Z1000000",
            "invoices": "Invoices!A1:Z1000000",
        }
    )
    credentials_secret: str = ""  # Secrets ref holding the refresh token


class GoogleSheetsConnector(ConnectorBase):
    source_type = "google_sheets"

    def __init__(self, config: GoogleSheetsConfig, tenant_id: str, source_id: str):
        super().__init__(config, tenant_id, source_id)
        self.config: GoogleSheetsConfig = config
        self._access_token: str | None = None

    async def authenticate(self) -> None:
        secret = load_secret(self.config.credentials_secret)
        if not secret or "refresh_token" not in secret:
            raise PermissionError("google_sheets source is not connected (no refresh token)")
        tokens = await refresh_access_token(secret["refresh_token"])
        self._access_token = tokens["access_token"]

    async def fetch_raw(self, dataset: str) -> pd.DataFrame:
        if self._access_token is None:
            await self.authenticate()
        rng = self.config.ranges[dataset]
        url = f"{SHEETS_API}/{self.config.spreadsheet_id}/values/{rng}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {self._access_token}"},
                params={
                    "valueRenderOption": "UNFORMATTED_VALUE",
                    "dateTimeRenderOption": "FORMATTED_STRING",
                },
            )
            if resp.status_code == 401:
                # token expired mid-flight → refresh once and retry
                await self.authenticate()
                resp = await client.get(
                    url, headers={"Authorization": f"Bearer {self._access_token}"}
                )
            resp.raise_for_status()
            values = resp.json().get("values", [])

        if not values:
            return pd.DataFrame()
        header, *rows = values
        width = len(header)
        rows = [r + [None] * (width - len(r)) for r in rows]  # pad ragged rows
        df = pd.DataFrame(rows, columns=[str(h).strip() for h in header])
        return self.map_columns(df, dataset)
