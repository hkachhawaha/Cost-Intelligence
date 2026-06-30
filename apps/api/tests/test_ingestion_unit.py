"""Unit tests for vendor fingerprinting and the idempotency row hash (no DB)."""

from __future__ import annotations

from app.connectors.base import ConnectorBase
from app.services.vendor_normalization import VendorNormalizationService


def _svc() -> VendorNormalizationService:
    # fingerprint/normalized_name are pure — no DB needed.
    return VendorNormalizationService(session=None, tenant_id="t")  # type: ignore[arg-type]


def test_fingerprint_order_independent_and_strips_suffixes():
    svc = _svc()
    assert svc.fingerprint("Acme Cloud Inc") == svc.fingerprint("Cloud, Acme LLC")
    assert svc.fingerprint("Acme Inc") == svc.fingerprint("ACME, LLC") == svc.fingerprint("Acme")


def test_fingerprint_distinguishes_real_vendors():
    svc = _svc()
    assert svc.fingerprint("Acme") != svc.fingerprint("Apex")


def test_row_hash_stable_for_same_natural_key():
    nk = ("invoice_number", "vendor_name")
    a = ConnectorBase.row_hash(
        {"invoice_number": "INV-1", "vendor_name": "Acme", "amount": 100}, nk
    )
    # Same natural key, different non-key field → same hash.
    b = ConnectorBase.row_hash(
        {"invoice_number": "INV-1", "vendor_name": "Acme", "amount": 999}, nk
    )
    assert a == b


def test_row_hash_fallback_when_key_incomplete():
    nk = ("po_number", "vendor_name", "amount", "spend_date")
    row = {"vendor_name": "Acme", "amount": 100}  # missing po_number, spend_date
    h1 = ConnectorBase.row_hash(row, nk)
    h2 = ConnectorBase.row_hash(dict(row), nk)
    assert h1 == h2 and len(h1) == 64  # deterministic full-row sha256
