"""Inbound data contracts (Pydantic v2) for the three core datasets.

Each connector validates raw rows against these before anything reaches the
canonical store. A row that fails is quarantined with its violations — never
silently dropped. `extra="allow"` lets unmapped source columns flow through to
the `extra` JSONB column so nothing is lost.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DataContractViolation(BaseModel):
    row_index: int
    field: str
    rule: str  # pydantic error type, e.g. 'missing', 'decimal_parsing'
    actual_value: str | None = None
    message: str


class ValidationResult(BaseModel):
    is_valid: bool
    valid_rows: list[dict] = Field(default_factory=list)
    violations: list[DataContractViolation] = Field(default_factory=list)
    quarantined_rows: list[dict] = Field(default_factory=list)


class ColumnMapping(BaseModel):
    """Maps a source sheet header to a canonical field name."""

    source_header: str
    canonical_field: str


def _currency_iso(v: str) -> str:
    v = v.strip().upper()
    if len(v) != 3 or not v.isalpha():
        raise ValueError("currency must be a 3-letter ISO-4217 code")
    return v


class InboundContract(BaseModel):
    model_config = ConfigDict(extra="allow")  # unmapped columns flow to `extra`

    # Required minimal set for a usable contract record.
    vendor_name: str
    acv: Decimal
    tcv: Decimal
    start_date: date
    end_date: date
    renewal_type: Literal["auto", "option", "none"]
    renewal_notice_days: int = 0
    currency: str = "USD"

    # Optional subset of the 95 (remainder accepted via extra / mapping).
    contract_number: str | None = None
    contract_type: str | None = None
    title: str | None = None
    entity_name: str | None = None
    uplift_pct: Decimal | None = None
    index_type: str | None = None
    indexed_share: Decimal | None = None
    yearly_commit: Decimal | None = None
    payment_term_days: int | None = None
    po_number: str | None = None
    category_l1: str | None = None
    category_l2: str | None = None

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        return _currency_iso(v)

    @field_validator("acv", "tcv")
    @classmethod
    def _non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("must be non-negative")
        return v

    @field_validator("renewal_notice_days")
    @classmethod
    def _notice_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("renewal_notice_days must be >= 0")
        return v

    @model_validator(mode="after")
    def _coherence(self) -> InboundContract:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on/after start_date")
        if self.indexed_share is not None and not (0 <= self.indexed_share <= 1):
            raise ValueError("indexed_share must be between 0 and 1")
        return self


class InboundSpendRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    vendor_name: str
    amount: Decimal
    spend_date: date
    currency: str = "USD"
    gl_code: str | None = None
    cost_center: str | None = None
    po_number: str | None = None
    entity_name: str | None = None
    description: str | None = None
    source_system: Literal["coupa", "oracle", "sap", "manual", "sheets"] = "sheets"

    @field_validator("amount")
    @classmethod
    def _amount_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("amount must be non-negative")
        return v

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        return _currency_iso(v)


class InboundInvoice(BaseModel):
    model_config = ConfigDict(extra="allow")

    vendor_name: str
    invoice_number: str
    invoice_date: date
    total_amount: Decimal
    currency: str = "USD"
    due_date: date | None = None
    payment_date: date | None = None
    status: Literal["paid", "open", "overdue"] = "open"
    po_number: str | None = None

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        return _currency_iso(v)

    @model_validator(mode="after")
    def _coherence(self) -> InboundInvoice:
        if self.due_date and self.due_date < self.invoice_date:
            raise ValueError("due_date must be on/after invoice_date")
        if self.total_amount < 0:
            raise ValueError("total_amount must be non-negative")
        return self


DATASET_CONTRACTS: dict[str, type[BaseModel]] = {
    "contracts": InboundContract,
    "spend_records": InboundSpendRecord,
    "invoices": InboundInvoice,
}
