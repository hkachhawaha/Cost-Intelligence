"""ERP connectors (§4.2) — Coupa, Oracle, SAP. Mappers normalize each vendor's raw row
shape into the canonical Inbound* data contracts before the shared validate() driver runs."""

from app.connectors.erp.mappers import CoupaMapper, OracleMapper, SapMapper

__all__ = ["CoupaMapper", "OracleMapper", "SapMapper"]
