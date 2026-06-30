"""Canonical vendor normalization (§7.3).

Folds vendor name variants ("Acme Inc", "ACME, LLC", "Acme") into one canonical
vendor via a deterministic fingerprint + Jaro-Winkler fuzzy match, recording
every raw spelling as an alias for lineage.
"""

from __future__ import annotations

import re
from uuid import UUID

from jellyfish import jaro_winkler_similarity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.vendor import Vendor, VendorAlias

_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|llp|ltd|limited|corp|corporation|co|company|"
    r"gmbh|sa|sas|plc|pte|pty|bv|ag|srl|spa)\b"
)
_PUNCT = re.compile(r"[^a-z0-9 ]")
_WS = re.compile(r"\s+")


class VendorNormalizationService:
    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    def normalized_name(self, name: str) -> str:
        s = name.lower().strip()
        s = _PUNCT.sub(" ", s)
        s = _SUFFIXES.sub("", s)
        return _WS.sub(" ", s).strip()

    def fingerprint(self, name: str) -> str:
        """Order-independent token signature ('Acme Cloud' == 'Cloud Acme')."""
        return " ".join(sorted(self.normalized_name(name).split()))

    async def get_or_create_canonical(
        self, raw_name: str, *, source: str = "sheets", threshold: float | None = None
    ) -> Vendor:
        threshold = threshold if threshold is not None else settings.vendor_dedup_threshold
        fp = self.fingerprint(raw_name)

        # 1. exact fingerprint hit
        existing = (
            (
                await self.session.execute(
                    select(Vendor).where(
                        Vendor.tenant_id == UUID(self.tenant_id),
                        Vendor.name_fingerprint == fp,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing:
            await self._record_alias(existing.id, raw_name, source)
            return existing

        # 2. fuzzy over candidates sharing a leading token (cheap blocking)
        lead = fp.split(" ")[0] if fp else ""
        candidates = (
            (
                await self.session.execute(
                    select(Vendor).where(
                        Vendor.tenant_id == UUID(self.tenant_id),
                        Vendor.name_fingerprint.like(f"{lead}%"),
                    )
                )
            )
            .scalars()
            .all()
        )
        best, best_score = None, 0.0
        for v in candidates:
            score = jaro_winkler_similarity(fp, v.name_fingerprint)
            if score > best_score:
                best, best_score = v, score
        if best and best_score >= threshold:
            await self._record_alias(best.id, raw_name, source)
            return best

        # 3. create a new canonical vendor
        vendor = Vendor(
            tenant_id=UUID(self.tenant_id),
            name=raw_name.strip(),
            normalized_name=self.normalized_name(raw_name),
            name_fingerprint=fp,
        )
        self.session.add(vendor)
        await self.session.flush()
        await self._record_alias(vendor.id, raw_name, source)
        return vendor

    async def _record_alias(self, vendor_id: UUID, raw_name: str, source: str) -> None:
        exists = (
            (
                await self.session.execute(
                    select(VendorAlias).where(
                        VendorAlias.tenant_id == UUID(self.tenant_id),
                        VendorAlias.raw_name == raw_name,
                    )
                )
            )
            .scalars()
            .first()
        )
        if exists:
            return
        self.session.add(
            VendorAlias(
                tenant_id=UUID(self.tenant_id),
                vendor_id=vendor_id,
                raw_name=raw_name,
                source=source,
            )
        )
        await self.session.flush()
