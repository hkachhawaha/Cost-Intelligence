"""S3 snapshot store for agent-run inputs/outputs (audit lineage, §7.3).

Best-effort: if no bucket is configured or aioboto3 isn't installed (local/dev/CI),
`write` is a no-op returning None — the AgentRun row still records status/confidence,
just without an S3 reference. In cloud, KMS-encrypted (+ Object-Lock WORM recommended).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app.core.config import settings

logger = logging.getLogger("snapshots")


class S3SnapshotStore:
    def __init__(self):
        self.bucket = settings.s3_bucket
        self.prefix = "agent-runs"

    async def write(self, tenant_id: str, run_id: str, kind: str, payload) -> str | None:
        if not self.bucket:
            return None  # no store configured (local/dev) — audit row still records the run
        try:
            import aioboto3
        except ModuleNotFoundError:  # pragma: no cover
            logger.debug("aioboto3 not installed; skipping S3 snapshot")
            return None
        ts = datetime.now(UTC).strftime("%Y/%m/%d")
        key = f"{self.prefix}/{tenant_id}/{ts}/{run_id}.{kind}.json"
        body = json.dumps(payload, default=str).encode()
        extra = {"ServerSideEncryption": "aws:kms"} if settings.snapshot_kms else {}
        session = aioboto3.Session()
        async with session.client("s3", region_name=settings.aws_region) as s3:
            await s3.put_object(
                Bucket=self.bucket, Key=key, Body=body, ContentType="application/json", **extra
            )
        return f"s3://{self.bucket}/{key}"
