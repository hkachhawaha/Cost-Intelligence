"""ConversationService (§5.5) — persist NirvanaI turns + fetch history.

Tenant-scoped via the RLS session; a conversation is only reused if it belongs to
the requesting tenant (defense in depth on top of RLS).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.models.nirvana import NirvanaConversation, NirvanaMessage


class ConversationService:
    async def get_or_create(
        self,
        session: AsyncSession,
        principal: Principal,
        conversation_id: str | None,
        module_context: str | None,
    ) -> NirvanaConversation:
        if conversation_id:
            conv = await session.get(NirvanaConversation, UUID(conversation_id))
            if conv and str(conv.tenant_id) == principal.tenant_id:
                return conv
        conv = NirvanaConversation(
            id=uuid4(),
            tenant_id=UUID(principal.tenant_id),
            user_id=UUID(principal.user_id),
            module_context=module_context,
        )
        session.add(conv)
        await session.flush()
        return conv

    async def append_turn(
        self,
        session: AsyncSession,
        conv: NirvanaConversation,
        *,
        role: str,
        content: str,
        intent: str | None = None,
        citations: list | None = None,
        grounded: bool | None = None,
        model_used: str | None = None,
        run_id: str | None = None,
        latency_ms: int | None = None,
    ) -> NirvanaMessage:
        msg = NirvanaMessage(
            id=uuid4(),
            tenant_id=conv.tenant_id,
            conversation_id=conv.id,
            role=role,
            content=content,
            intent=intent,
            citations=citations or [],
            grounded=grounded,
            model_used=model_used,
            run_id=UUID(run_id) if run_id else None,
            latency_ms=latency_ms,
        )
        session.add(msg)
        await session.flush()
        return msg

    async def history(
        self, session: AsyncSession, conversation_id: str, limit: int = 50
    ) -> list[NirvanaMessage]:
        rows = await session.scalars(
            select(NirvanaMessage)
            .where(NirvanaMessage.conversation_id == UUID(conversation_id))
            .order_by(NirvanaMessage.created_at)
            .limit(limit)
        )
        return list(rows.all())


conversation_service = ConversationService()
