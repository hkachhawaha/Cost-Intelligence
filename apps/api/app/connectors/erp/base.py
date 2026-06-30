"""Shared ERP connector base. Holds a vendor `ErpMapper` and overrides `map_columns` so the
raw fetched DataFrame is reshaped into canonical Inbound* rows before the inherited
`validate()` driver runs. Subclasses only implement `authenticate()` + `fetch_raw()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.connectors.base import ConnectorBase, ConnectorConfig
from app.connectors.erp.mappers import ErpMapper

_DATASET_INVOICES = "invoices"
_DATASET_SPEND = "spend_records"


@dataclass
class ErpConnectorConfig(ConnectorConfig):
    base_url: str = ""
    credentials_secret: str = ""  # KMS/secrets ref — never a raw secret
    column_mappings: dict = field(default_factory=dict)


class ErpConnectorBase(ConnectorBase):
    mapper: ErpMapper

    def map_columns(self, df: pd.DataFrame, dataset: str) -> pd.DataFrame:
        """Apply the vendor mapper row-by-row to produce canonical columns."""
        if df.empty:
            return df
        rows = df.to_dict(orient="records")
        if dataset == _DATASET_INVOICES:
            canonical = self.mapper.map_invoices(rows)
        elif dataset == _DATASET_SPEND:
            canonical = self.mapper.map_spend_records(rows)
        else:
            return df  # unknown dataset — leave untouched
        return pd.DataFrame(canonical)
