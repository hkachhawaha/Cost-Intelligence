"""Unit tests for inbound data contracts (no DB)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.data_contracts import InboundContract, InboundInvoice, InboundSpendRecord


def test_inbound_contract_valid_normalizes_currency():
    c = InboundContract(
        vendor_name="Acme",
        acv="120000",
        tcv="360000",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        renewal_type="auto",
        currency="usd",
    )
    assert c.currency == "USD"
    assert c.acv == Decimal("120000")
    assert c.renewal_notice_days == 0  # default


def test_inbound_contract_end_before_start_rejected():
    with pytest.raises(ValidationError, match="end_date must be on/after start_date"):
        InboundContract(
            vendor_name="Acme",
            acv="1",
            tcv="1",
            start_date=date(2026, 12, 31),
            end_date=date(2026, 1, 1),
            renewal_type="none",
        )


def test_inbound_contract_bad_currency_rejected():
    with pytest.raises(ValidationError, match="ISO-4217"):
        InboundContract(
            vendor_name="Acme",
            acv="1",
            tcv="1",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 2, 1),
            renewal_type="none",
            currency="Dollars",
        )


def test_inbound_spend_negative_amount_rejected():
    with pytest.raises(ValidationError, match="non-negative"):
        InboundSpendRecord(vendor_name="Acme", amount="-5", spend_date=date(2026, 1, 1))


def test_inbound_invoice_due_before_invoice_rejected():
    with pytest.raises(ValidationError, match="due_date must be on/after"):
        InboundInvoice(
            vendor_name="Acme",
            invoice_number="INV-1",
            invoice_date=date(2026, 2, 1),
            total_amount="100",
            due_date=date(2026, 1, 1),
        )
