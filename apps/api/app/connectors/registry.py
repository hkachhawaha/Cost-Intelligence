"""Connector registry — maps a DataSource row to a built connector instance."""

from __future__ import annotations

from uuid import UUID

from app.connectors.base import ConnectorBase
from app.connectors.erp.base import ErpConnectorConfig
from app.connectors.erp.coupa import CoupaConnector
from app.connectors.erp.oracle import OracleConnector
from app.connectors.erp.sap import SapConnector
from app.connectors.google_sheets import GoogleSheetsConfig, GoogleSheetsConnector
from app.core.database import session_for_tenant
from app.models.staging import DataSource
from app.schemas.data_contracts import ColumnMapping

_REGISTRY: dict[str, type[ConnectorBase]] = {
    "google_sheets": GoogleSheetsConnector,
    "coupa": CoupaConnector,
    "oracle": OracleConnector,
    "sap": SapConnector,
}

_ERP_CONNECTORS: dict[str, type[ConnectorBase]] = {
    "coupa": CoupaConnector,
    "oracle": OracleConnector,
    "sap": SapConnector,
}


async def build_connector(tenant_id: str, source_id: str) -> ConnectorBase:
    async with await session_for_tenant(tenant_id) as session:
        ds = await session.get(DataSource, UUID(source_id))
        if ds is None:
            raise ValueError(f"data source {source_id} not found")
        source_type = ds.source_type
        config = dict(ds.config or {})
        credentials_secret = ds.credentials_secret or ""

    if source_type == "google_sheets":
        cfg = GoogleSheetsConfig(
            spreadsheet_id=config["spreadsheet_id"],
            ranges=config.get("ranges") or GoogleSheetsConfig(column_mappings={}).ranges,
            credentials_secret=credentials_secret,
            column_mappings={
                k: [ColumnMapping(**m) for m in v]
                for k, v in config.get("column_mappings", {}).items()
            },
        )
        return GoogleSheetsConnector(cfg, tenant_id, source_id)
    if source_type in _ERP_CONNECTORS:
        erp_cfg = ErpConnectorConfig(
            base_url=config.get("base_url", ""),
            credentials_secret=credentials_secret,
            column_mappings={
                k: [ColumnMapping(**m) for m in v]
                for k, v in config.get("column_mappings", {}).items()
            },
        )
        return _ERP_CONNECTORS[source_type](erp_cfg, tenant_id, source_id)
    raise ValueError(f"unsupported source_type {source_type}")
