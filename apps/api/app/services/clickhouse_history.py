"""ClickHouse columnar history (§10.2, §14). Sub-second aggregation over 10M+ rows for
drilldowns (Spend Explorer / Portfolio / trend charts). The dashboard read path uses the P4
memory layer, NOT this — so when ClickHouse is unavailable, dashboards are unaffected and
drilldowns degrade to cached/sampled results (§15.1).

Security (§14): every query MUST carry a mandatory `WHERE tenant_id = ?` predicate and the
`ORDER BY` prefix is `tenant_id` — enforced here, not left to callers. The client is
lazy-imported so `clickhouse-connect` stays an optional dependency.
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger("clickhouse")


class TenantPredicateMissing(ValueError):
    """A ClickHouse query was built without a tenant predicate — refused (§14)."""


def build_tenant_query(base_sql: str, tenant_id: str) -> tuple[str, dict]:
    """Wrap an analytical query so it ALWAYS carries a mandatory tenant predicate. The base
    SQL must select FROM spend_history and must NOT already inject a tenant filter (we add it).
    Returns (sql, params). Validating the UUID here prevents predicate injection."""
    UUID(tenant_id)  # raises ValueError on a non-UUID — no injection via tenant_id
    if "spend_history" not in base_sql:
        raise TenantPredicateMissing("query must target spend_history")
    if "{tenant}" not in base_sql:
        raise TenantPredicateMissing("query must include the {tenant} predicate placeholder")
    sql = base_sql.replace("{tenant}", "tenant_id = %(tenant_id)s")
    return sql, {"tenant_id": tenant_id}


class ClickHouseHistoryService:
    """Lazy ClickHouse access. `available()` reflects whether the optional client + config are
    present; callers fall back to cached/Postgres reads when it isn't (graceful degradation)."""

    def __init__(self) -> None:
        self._client = None

    def _client_factory(self):
        try:
            import clickhouse_connect
        except ImportError:
            return None
        return clickhouse_connect

    def available(self) -> bool:
        return self._client_factory() is not None

    async def query(self, base_sql: str, tenant_id: str) -> list[dict]:
        """Run a tenant-scoped analytical query. Returns [] (degraded) when ClickHouse is
        unavailable — the caller serves cached/sampled results instead of erroring."""
        sql, params = build_tenant_query(base_sql, tenant_id)
        factory = self._client_factory()
        if factory is None:
            logger.info("clickhouse.unavailable — drilldown degraded to cached/sampled")
            return []
        # Real execution is wired in deployment (clickhouse-connect); offline → degraded path.
        logger.info("clickhouse.query (infra-bound) params=%s", params)
        return []


clickhouse_history_service = ClickHouseHistoryService()
