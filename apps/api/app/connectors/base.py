"""ConnectorBase — the template every source connector implements.

Subclasses implement `authenticate()` and `fetch_raw()`. The base provides
`map_columns()`, the deterministic idempotency `row_hash()`, and the shared
`validate()` driver that splits a batch into valid rows + violations + quarantine
candidates against a Pydantic data contract.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd
from pydantic import BaseModel, ValidationError

from app.schemas.data_contracts import (
    ColumnMapping,
    DataContractViolation,
    ValidationResult,
)


@dataclass
class ConnectorConfig:
    """Base config; subclasses extend with source-specific fields."""

    column_mappings: dict[str, list[ColumnMapping]]  # per-dataset header→field maps


@dataclass
class IngestionResult:
    dataset_type: str
    validation: ValidationResult


class ConnectorBase(ABC):
    source_type: str = "base"

    def __init__(self, config: ConnectorConfig, tenant_id: str, source_id: str):
        self.config = config
        self.tenant_id = tenant_id
        self.source_id = source_id

    # ---- subclass responsibilities ----
    @abstractmethod
    async def authenticate(self) -> None:
        """Establish credentials (OAuth refresh, API key, etc.)."""

    @abstractmethod
    async def fetch_raw(self, dataset: str) -> pd.DataFrame:
        """Return the raw rows for a dataset as a DataFrame (header → columns)."""

    # ---- shared behavior ----
    def map_columns(self, df: pd.DataFrame, dataset: str) -> pd.DataFrame:
        """Rename source headers to canonical field names. Unmapped columns are
        kept (they flow into the Pydantic `extra` and the `extra` JSONB)."""
        mappings = self.config.column_mappings.get(dataset, [])
        rename = {m.source_header: m.canonical_field for m in mappings}
        df = df.rename(columns=rename)
        return df.replace({"": None})

    @staticmethod
    def row_hash(row: dict, natural_key: tuple[str, ...]) -> str:
        """Stable idempotency hash. Prefers a natural key; falls back to the full
        row when the key is incomplete. Excludes any prior hash column."""
        key_parts = [str(row.get(k, "")) for k in natural_key]
        if all(key_parts):
            basis = "|".join(key_parts)
        else:
            payload = {k: v for k, v in row.items() if k != "source_row_hash"}
            basis = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()

    async def validate(self, df: pd.DataFrame, schema: type[BaseModel]) -> ValidationResult:
        valid_rows: list[dict] = []
        quarantined: list[dict] = []
        violations: list[DataContractViolation] = []

        for idx, raw in enumerate(df.to_dict(orient="records")):
            clean = {k: (None if pd.isna(v) else v) for k, v in raw.items()}
            row_hash = clean.get("source_row_hash")
            payload = {k: v for k, v in clean.items() if k != "source_row_hash"}
            try:
                model = schema(**payload)
                dumped = model.model_dump()
                if row_hash is not None:
                    dumped["source_row_hash"] = row_hash
                valid_rows.append(dumped)
            except ValidationError as exc:
                for err in exc.errors():
                    loc = err.get("loc", ["<row>"])
                    violations.append(
                        DataContractViolation(
                            row_index=idx,
                            field=str(loc[0]) if loc else "<row>",
                            rule=err.get("type", "unknown"),
                            actual_value=str(err.get("input"))[:200],
                            message=err.get("msg", ""),
                        )
                    )
                quarantined.append(clean)

        return ValidationResult(
            is_valid=len(violations) == 0,
            valid_rows=valid_rows,
            violations=violations,
            quarantined_rows=quarantined,
        )
