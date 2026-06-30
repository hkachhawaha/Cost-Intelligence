"""EmbeddingsService — chunk contracts/clauses, embed via gemini-embedding-001,
upsert to pgvector (Store 2). Queried by NirvanaI RAG in Phase 6.

`google-genai` is imported lazily and the whole step is skipped when no
`GEMINI_API_KEY` is configured (local/dev/CI) — embeddings are non-fatal to a sync
(`EMBEDDING_FATAL_TO_SYNC=false`); the structured KPI snapshot is the operational path.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contract import Contract, ContractClause
from app.models.memory import ContractEmbedding

logger = logging.getLogger("embeddings")

MAX_CHUNK_CHARS = 2000
CHUNK_OVERLAP = 200


class EmbeddingsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def embed_tenant(self, tenant_id: str, *, memory_version: int) -> int:
        if not settings.gemini_api_key:
            logger.info("embeddings skipped (no GEMINI_API_KEY) tenant=%s", tenant_id)
            return 0
        try:
            from google import genai
            from google.genai import types
        except ModuleNotFoundError:  # pragma: no cover
            logger.warning("google-genai not installed; skipping embeddings")
            return 0

        client = genai.Client(api_key=settings.gemini_api_key)
        contracts = (await self.session.scalars(select(Contract))).all()
        clauses_by_contract: dict[UUID, list[ContractClause]] = {}
        for cl in (await self.session.scalars(select(ContractClause))).all():
            clauses_by_contract.setdefault(cl.contract_id, []).append(cl)

        # Supersede prior embeddings for this tenant (RLS scopes the delete).
        await self.session.execute(delete(ContractEmbedding))
        await self.session.commit()

        total = 0
        for contract in contracts:
            chunks = self._chunk_contract(contract, clauses_by_contract.get(contract.id, []))
            if not chunks:
                continue
            resp = await client.aio.models.embed_content(
                model=settings.embedding_model,
                contents=[c["text"] for c in chunks],
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",  # asymmetric: documents at index time
                    output_dimensionality=settings.embedding_dim,  # MRL truncation to 1536
                ),
            )
            for chunk, emb in zip(chunks, resp.embeddings or [], strict=False):
                self.session.add(
                    ContractEmbedding(
                        tenant_id=UUID(tenant_id),
                        contract_id=contract.id,
                        clause_id=chunk.get("clause_id"),
                        # source/source_id (Phase 6): source_id is the authorizable contract
                        # so RAG RBAC scoping filters on it before the vector search.
                        source="clause" if chunk["type"] == "clause" else "contract",
                        source_id=contract.id,
                        chunk_index=chunk["index"],
                        chunk_text=chunk["text"],
                        chunk_type=chunk["type"],
                        embedding=emb.values,
                        model=settings.embedding_model,
                        memory_version=memory_version,
                    )
                )
                total += 1
            await self.session.commit()

        logger.info("embeddings.embed_tenant tenant=%s chunks=%s", tenant_id, total)
        return total

    def _chunk_contract(self, contract: Contract, clauses: list[ContractClause]) -> list[dict]:
        chunks: list[dict] = []
        idx = 0
        header = (
            f"Contract {contract.id} vendor={contract.vendor_id} ACV={contract.acv} "
            f"TCV={contract.tcv} term={contract.start_date}..{contract.end_date} "
            f"renewal={contract.renewal_type} notice_days={contract.renewal_notice_days} "
            f"uplift={contract.uplift_pct} index={contract.index_type}"
        )
        chunks.append({"index": idx, "text": header, "type": "summary"})
        idx += 1
        for clause in clauses:
            for window in self._window(clause.raw_text):
                chunks.append(
                    {"index": idx, "text": window, "type": "clause", "clause_id": clause.id}
                )
                idx += 1
        return chunks

    @staticmethod
    def _window(text: str | None) -> list[str]:
        if not text:
            return []
        out, start = [], 0
        while start < len(text):
            out.append(text[start : start + MAX_CHUNK_CHARS])
            start += MAX_CHUNK_CHARS - CHUNK_OVERLAP
        return out
