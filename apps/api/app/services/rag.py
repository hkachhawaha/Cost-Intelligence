"""RAGService (§5.2) — gemini-embedding-001 query embedding, RBAC + entity-scoped
pgvector similarity search, top-k retrieve + Python rerank.

Access control is enforced BEFORE retrieval (§12.3): the authorized-contract set is
computed from role + entity and the pgvector WHERE clause filters on it, so an
unauthorized contract's embedding is never even ranked. The Gemini client is created
lazily; without a `GEMINI_API_KEY` retrieval degrades to empty (analysis still works
from memory), and `_authorized_contract_ids` remains fully usable for RBAC tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.config import settings

logger = logging.getLogger("nirvana.rag")

_PORTFOLIO_ROLES = {"portfolio_admin", "cfo", "admin"}


@dataclass
class RetrievedChunk:
    source: str  # 'contract'|'clause'|'opportunity'|'interaction'|'memory'
    source_id: str
    text: str
    distance: float  # cosine distance (lower = closer)
    impact: float | None  # opportunity $ impact, if applicable (drives rerank)
    label: str  # human-readable citation label


class RAGService:
    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def retrieve(
        self,
        query: str,
        *,
        session: AsyncSession,
        principal: Principal,
        k: int | None = None,
    ) -> list[RetrievedChunk]:
        k = k or settings.nirvana_rag_top_k
        if not settings.gemini_api_key:
            logger.info("rag.retrieve skipped (no GEMINI_API_KEY) tenant=%s", principal.tenant_id)
            return []

        # 1) Embed the query (gemini-embedding-001, asymmetric RETRIEVAL_QUERY).
        from google.genai import types

        emb = await self._get_client().aio.models.embed_content(
            model=settings.embedding_model,
            contents=[query],
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=settings.embedding_dim,
            ),
        )
        qvec = (emb.embeddings or [None])[0]
        if qvec is None:
            return []
        qvec_literal = "[" + ",".join(str(x) for x in qvec.values) + "]"

        # 2) Resolve the RBAC- and entity-authorized contract set BEFORE search.
        authorized = await self._authorized_contract_ids(session, principal)
        if not authorized:
            return []

        # 3) Vector search — RLS (tenant) + entity scope enforced in the WHERE clause.
        rows = await session.execute(
            text(
                """
                SELECT source, source_id, chunk_text,
                       (embedding <=> CAST(:qvec AS vector)) AS distance
                FROM memory_embeddings
                WHERE source = 'opportunity'
                   OR source_id = ANY(CAST(:authorized AS uuid[]))
                ORDER BY embedding <=> CAST(:qvec AS vector)
                LIMIT :overscan
                """
            ),
            {
                "qvec": qvec_literal,
                "authorized": authorized,
                "overscan": k * settings.nirvana_rag_overscan,
            },
        )
        chunks = await self._hydrate(session, rows.mappings().all(), authorized)

        # 4) Rerank in Python (no second model call): distance + opportunity-impact weight.
        return self._rerank(chunks)[:k]

    async def _authorized_contract_ids(
        self, session: AsyncSession, principal: Principal
    ) -> list[str]:
        """RBAC + ABAC entity scope. portfolio_admin/cfo/admin see all; others scoped to entity."""
        if principal.role in _PORTFOLIO_ROLES:
            rows = await session.execute(text("SELECT id FROM contracts"))
        else:
            rows = await session.execute(
                text(
                    "SELECT id FROM contracts "
                    "WHERE entity_id = CAST(:eid AS uuid) OR entity_id IS NULL"
                ),
                {"eid": principal.entity_id},
            )
        return [str(r[0]) for r in rows.all()]

    async def _hydrate(self, session, rows, authorized: list[str]) -> list[RetrievedChunk]:
        out: list[RetrievedChunk] = []
        for r in rows:
            impact, label = None, r["source"]
            if r["source"] == "opportunity":
                opp = await session.execute(
                    text(
                        """SELECT impact, type, contract_id FROM opportunities
                           WHERE id = CAST(:oid AS uuid)
                             AND (contract_id = ANY(CAST(:auth AS uuid[]))
                                  OR contract_id IS NULL)"""
                    ),
                    {"oid": str(r["source_id"]), "auth": authorized},
                )
                row = opp.mappings().first()
                if row is None:
                    continue  # opportunity not authorized → drop
                impact = float(row["impact"])
                label = f"Opportunity {row['type']} (${impact:,.0f})"
            out.append(
                RetrievedChunk(
                    source=r["source"],
                    source_id=str(r["source_id"]),
                    text=r["chunk_text"],
                    distance=float(r["distance"]),
                    impact=impact,
                    label=label,
                )
            )
        return out

    def _rerank(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []
        max_impact = max((c.impact or 0) for c in chunks) or 1.0

        def score(c: RetrievedChunk) -> float:
            relevance = 1.0 - c.distance  # cosine sim
            impact_boost = 0.25 * ((c.impact or 0) / max_impact)
            return relevance + impact_boost

        return sorted(chunks, key=score, reverse=True)


rag_service = RAGService()
