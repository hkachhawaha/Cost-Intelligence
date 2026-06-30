"""ERP → canonical mappers (§4.2). Pure, deterministic transforms (no I/O, no LLM): each
maps one vendor's raw row dict into the fields of an Inbound* data contract. Validation
itself happens later via the connector's `validate()`; these only rename/reshape/normalize.

Keeping the transform pure makes it the unit-testable heart of each ERP connector.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


def _iso_date(value: object) -> str | None:
    """Normalize an ERP date to YYYY-MM-DD. Handles ISO datetimes (slice the date part)
    and SAP's compact YYYYMMDD. Returns None for empty values; passes through otherwise."""
    if value is None or value == "":
        return None
    s = str(value).strip()
    if len(s) == 8 and s.isdigit():  # SAP BLDAT style: 20260315
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if "T" in s:  # ISO datetime → keep date component only
        return s.split("T", 1)[0]
    return s[:10] if len(s) >= 10 else s


def _dig(row: dict, *path, default=None):
    """Safely walk a nested dict by key path (Coupa nests supplier/currency objects)."""
    cur: object = row
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


class ErpMapper(ABC):
    """Common contract: each vendor maps raw rows for invoices and spend records."""

    source_system: str = "manual"
    # Per-vendor raw status token → canonical Inbound status (paid|open|overdue).
    INVOICE_STATUS_MAP: dict[str, str] = {}

    def map_status(self, raw: object) -> str:
        token = str(raw or "").strip().lower()
        return self.INVOICE_STATUS_MAP.get(token, "open")

    @abstractmethod
    def map_invoice(self, row: dict) -> dict:
        """Raw invoice row → InboundInvoice field dict."""

    @abstractmethod
    def map_spend(self, row: dict) -> dict:
        """Raw spend/expense row → InboundSpendRecord field dict."""

    def map_invoices(self, rows: list[dict]) -> list[dict]:
        return [self.map_invoice(r) for r in rows]

    def map_spend_records(self, rows: list[dict]) -> list[dict]:
        return [self.map_spend(r) for r in rows]


class CoupaMapper(ErpMapper):
    """Coupa REST shapes: hyphenated keys, nested supplier/currency objects."""

    source_system = "coupa"
    INVOICE_STATUS_MAP = {
        "paid": "paid", "voided": "open", "draft": "open", "approved": "open",
        "pending_receipt": "open", "disputed": "overdue", "overdue": "overdue",
    }

    def map_invoice(self, row: dict) -> dict:
        return {
            "vendor_name": _dig(row, "supplier", "name") or row.get("supplier-name") or "",
            "invoice_number": str(row.get("invoice-number") or row.get("id") or ""),
            "invoice_date": _iso_date(row.get("invoice-date")),
            "total_amount": str(row.get("total") or row.get("total-with-taxes") or "0"),
            "currency": _dig(row, "currency", "code", default="USD"),
            "status": self.map_status(row.get("status")),
            "po_number": row.get("po-number") or _dig(row, "purchase-order", "po-number"),
            "source_system": self.source_system,
        }

    def map_spend(self, row: dict) -> dict:
        return {
            "vendor_name": _dig(row, "supplier", "name") or row.get("supplier-name") or "",
            "amount": str(row.get("total") or row.get("amount") or "0"),
            "spend_date": _iso_date(row.get("accounting-date") or row.get("expense-date")),
            "currency": _dig(row, "currency", "code", default="USD"),
            "gl_code": _dig(row, "account", "code") or row.get("account-code"),
            "cost_center": row.get("department") or _dig(row, "department", "name"),
            "po_number": row.get("po-number"),
            "description": row.get("description"),
            "source_system": self.source_system,
        }


class OracleMapper(ErpMapper):
    """Oracle Fusion/EBS shapes: UPPER_SNAKE_CASE flat columns."""

    source_system = "oracle"
    INVOICE_STATUS_MAP = {
        "y": "paid", "paid": "paid", "n": "open", "unpaid": "open",
        "partial": "open", "overdue": "overdue",
    }

    def map_invoice(self, row: dict) -> dict:
        return {
            "vendor_name": row.get("VENDOR_NAME") or row.get("SUPPLIER_NAME") or "",
            "invoice_number": str(row.get("INVOICE_NUM") or row.get("INVOICE_NUMBER") or ""),
            "invoice_date": _iso_date(row.get("INVOICE_DATE")),
            "total_amount": str(row.get("INVOICE_AMOUNT") or row.get("AMOUNT") or "0"),
            "currency": row.get("INVOICE_CURRENCY_CODE") or "USD",
            "status": self.map_status(row.get("PAYMENT_STATUS_FLAG")),
            "po_number": row.get("PO_NUMBER"),
            "source_system": self.source_system,
        }

    def map_spend(self, row: dict) -> dict:
        return {
            "vendor_name": row.get("SUPPLIER_NAME") or row.get("VENDOR_NAME") or "",
            "amount": str(row.get("AMOUNT") or row.get("ENTERED_AMOUNT") or "0"),
            "spend_date": _iso_date(row.get("GL_DATE") or row.get("ACCOUNTING_DATE")),
            "currency": row.get("CURRENCY_CODE") or "USD",
            "gl_code": row.get("GL_ACCOUNT") or row.get("CODE_COMBINATION"),
            "cost_center": row.get("COST_CENTER") or row.get("DEPARTMENT"),
            "po_number": row.get("PO_NUMBER"),
            "description": row.get("DESCRIPTION"),
            "source_system": self.source_system,
        }


class SapMapper(ErpMapper):
    """SAP S/4 & Ariba shapes: technical field codes (BUKRS/LIFNR/WRBTR) or readable aliases."""

    source_system = "sap"
    INVOICE_STATUS_MAP = {
        "p": "paid", "paid": "paid", "cleared": "paid", "o": "open",
        "open": "open", "parked": "open", "blocked": "overdue", "overdue": "overdue",
    }

    def map_invoice(self, row: dict) -> dict:
        return {
            "vendor_name": row.get("Supplier") or row.get("LIFNR_NAME") or row.get("NAME1") or "",
            "invoice_number": str(row.get("DocumentNumber") or row.get("BELNR") or ""),
            "invoice_date": _iso_date(row.get("DocumentDate") or row.get("BLDAT")),
            "total_amount": str(row.get("Amount") or row.get("WRBTR") or "0"),
            "currency": row.get("Currency") or row.get("WAERS") or "USD",
            "status": self.map_status(row.get("PaymentStatus") or row.get("AUGBL_STATUS")),
            "po_number": row.get("PurchaseOrder") or row.get("EBELN"),
            "source_system": self.source_system,
        }

    def map_spend(self, row: dict) -> dict:
        return {
            "vendor_name": row.get("Supplier") or row.get("NAME1") or "",
            "amount": str(row.get("Amount") or row.get("WRBTR") or "0"),
            "spend_date": _iso_date(row.get("PostingDate") or row.get("BUDAT")),
            "currency": row.get("Currency") or row.get("WAERS") or "USD",
            "gl_code": row.get("GLAccount") or row.get("HKONT"),
            "cost_center": row.get("CostCenter") or row.get("KOSTL"),
            "po_number": row.get("PurchaseOrder") or row.get("EBELN"),
            "description": row.get("Text") or row.get("SGTXT"),
            "source_system": self.source_system,
        }
