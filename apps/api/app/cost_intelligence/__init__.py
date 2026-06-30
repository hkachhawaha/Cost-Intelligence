"""Cost Intelligence — the Google-Sheets-driven, single-workspace product layer.

Ingestion (read the connected workbook) → relationship intelligence (link contracts ↔ invoices
↔ spend) → insight generation (deterministic detection + KPIs) → Agent Memory (the app and
NirvanAI operate from memory, not the live sheet). A manual Refresh re-reads and rebuilds.
"""
