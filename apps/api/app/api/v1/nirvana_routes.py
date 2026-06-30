"""NirvanaI API (§6) — chat (SSE/JSON), generate-doc, draft edit/send, history.

Chat runs the LangGraph agent inside an immutable AgentRun; document generation is
human-gated (drafts created in status='draft', never auto-sent — §5.7). All LLM work
flows through the ModelGateway; figures are groundedness-validated.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import DOC_SKELETONS, GROUNDED_QA_SYSTEM
from app.core.agent_run import agent_run
from app.core.audit import record_audit_event
from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.model_gateway import RateLimitExceeded, model_gateway
from app.core.rbac import require_permission
from app.models.memory import TenantMemory
from app.models.nirvana import DocumentDraft, NirvanaConversation
from app.schemas.nirvana import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationListItem,
    ConversationListResponse,
    DocDraftResponse,
    DraftListItem,
    DraftListResponse,
    DraftPatch,
    GenerateDocRequest,
    MessageOut,
)
from app.services.conversation import conversation_service
from app.services.documents import TEMPLATES, DocumentNotAuthorizedError, document_service
from app.services.groundedness import groundedness_validator

router = APIRouter(prefix="/nirvana", tags=["nirvana"])

_USE = Depends(require_permission("nirvana:use"))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chat", dependencies=[_USE])
async def chat(
    body: ChatRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
):
    if not body.message or not body.message.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "message is required")

    # 503 when the tenant has never run an initial sync (no memory to ground answers).
    if await session.get(TenantMemory, UUID(principal.tenant_id)) is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Run an initial sync to enable NirvanaI."
        )

    from app.agents.nirvana import nirvana_graph

    history = (
        await conversation_service.history(session, body.conversation_id)
        if body.conversation_id
        else []
    )
    t0 = time.perf_counter()
    try:
        async with agent_run(
            tenant_id=principal.tenant_id, agent="nirvana_assistant", trigger="user_request"
        ) as run:
            run_id = str(run.run_id)
            out = await nirvana_graph.ainvoke(
                {
                    "tenant_id": principal.tenant_id,
                    "principal": principal,
                    "message": body.message,
                    "module_context": body.module_context,
                    "history": [{"role": m.role, "content": m.content} for m in history],
                    "run_id": run_id,
                }
            )
            run.set_outputs({"intent": out.get("intent"), "grounded": out.get("grounded")})
    except RateLimitExceeded as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "You've reached the assistant usage cap for now. Please try again shortly.",
        ) from exc

    latency = int((time.perf_counter() - t0) * 1000)
    conv = await conversation_service.get_or_create(
        session, principal, body.conversation_id, body.module_context
    )
    await conversation_service.append_turn(session, conv, role="user", content=body.message)
    citations = out.get("citations", [])
    assistant = await conversation_service.append_turn(
        session,
        conv,
        role="assistant",
        content=out["final_text"],
        intent=out.get("intent"),
        citations=citations,
        grounded=out.get("grounded"),
        model_used="gemini-2.5-pro",
        run_id=run_id,
        latency_ms=latency,
    )
    await session.commit()

    payload = ChatResponse(
        conversation_id=str(conv.id),
        message_id=str(assistant.id),
        answer=out["final_text"],
        intent=out.get("intent", "qa"),
        grounded=bool(out.get("grounded")),
        citations=citations,
        latency_ms=latency,
    )

    # Stream only when the client explicitly opts in (EventSource sends this Accept);
    # default to JSON so plain fetch/SDK callers get a parseable body.
    if "text/event-stream" in (request.headers.get("accept") or ""):

        async def _stream() -> AsyncIterator[str]:
            yield _sse("intent", {"intent": payload.intent, "model": "gemini-2.5-flash"})
            yield _sse("token", {"text": payload.answer})
            yield _sse("done", payload.model_dump())

        return StreamingResponse(_stream(), media_type="text/event-stream")

    return JSONResponse(payload.model_dump())


@router.post(
    "/generate-doc",
    status_code=status.HTTP_201_CREATED,
    response_model=DocDraftResponse,
    dependencies=[_USE],
)
async def generate_doc(
    body: GenerateDocRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> DocDraftResponse:
    if body.template not in TEMPLATES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown template {body.template}")
    try:
        ctx = await document_service.assemble_context(
            body.template, body.context.id, session=session, principal=principal
        )
    except DocumentNotAuthorizedError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "context record not found or not authorized"
        ) from exc

    skeleton = DOC_SKELETONS[body.template]
    ctx_text = "\n".join(f"- {k}: {v}" for k, v in ctx.items() if v is not None)
    async with agent_run(
        tenant_id=principal.tenant_id, agent="document_action", trigger="user_request"
    ) as run:
        run_id = run.run_id
        res = await model_gateway.complete(
            "complex",
            skeleton.format(context=ctx_text),
            tenant_id=principal.tenant_id,
            purpose="document_generate",
            system=GROUNDED_QA_SYSTEM,
            max_tokens=2048,
            run_id=str(run_id),
        )
        outcome = groundedness_validator.validate(res.text, [ctx])
        run.set_outputs({"grounded": outcome.ok, "template": body.template})

    if not outcome.ok:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "generated draft failed groundedness validation"
        )

    title = TEMPLATES[body.template].title_tpl.format(
        vendor=ctx.get("vendor_name", "Vendor"), category=ctx.get("category", "Category")
    )
    figure = ctx.get("impact") or ctx.get("total_spend")
    citations = [
        {
            "type": body.context.type,
            "record_id": body.context.id,
            "label": title,
            "figure": str(figure) if figure is not None else None,
        }
    ]
    draft = DocumentDraft(
        id=uuid4(),
        tenant_id=UUID(principal.tenant_id),
        user_id=UUID(principal.user_id),
        conversation_id=UUID(body.conversation_id) if body.conversation_id else None,
        template=body.template,
        context_ref=body.context.model_dump(),
        title=title,
        body_markdown=res.text,
        citations=citations,
        status="draft",
        run_id=run_id,
    )
    session.add(draft)
    await session.commit()
    return DocDraftResponse(
        draft_id=str(draft.id),
        template=draft.template,
        title=draft.title,
        body_markdown=draft.body_markdown,
        citations=citations,
        status=draft.status,
        editable=True,
    )


@router.patch("/drafts/{draft_id}", response_model=DocDraftResponse, dependencies=[_USE])
async def patch_draft(
    draft_id: str,
    body: DraftPatch,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> DocDraftResponse:
    draft = await session.get(DocumentDraft, UUID(draft_id))
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    if draft.status == "sent":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "sent drafts are immutable; create a new draft"
        )

    if body.body_markdown is not None:
        draft.body_markdown = body.body_markdown
    if body.title is not None:
        draft.title = body.title
    if body.status == "sent":
        # HUMAN action — the platform never sets 'sent' itself (§5.7, §11.5).
        draft.status = "sent"
        draft.sent_by = UUID(principal.user_id)
        draft.sent_at = datetime.now(UTC)
        await record_audit_event(
            session,
            tenant_id=principal.tenant_id,
            event_type="document.sent",
            actor="human",
            actor_user_id=UUID(principal.user_id),
            payload={
                "draft_id": str(draft.id),
                "template": draft.template,
                "sent_by": principal.user_id,
            },
            run_id=draft.run_id,
        )
    elif body.status:
        draft.status = body.status
    await session.commit()
    return DocDraftResponse(
        draft_id=str(draft.id),
        template=draft.template,
        title=draft.title,
        body_markdown=draft.body_markdown,
        citations=draft.citations,
        status=draft.status,
        editable=draft.status != "sent",
    )


@router.get("/drafts", response_model=DraftListResponse, dependencies=[_USE])
async def list_drafts(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> DraftListResponse:
    rows = (
        await session.scalars(select(DocumentDraft).order_by(desc(DocumentDraft.created_at)))
    ).all()
    return DraftListResponse(
        drafts=[
            DraftListItem(
                draft_id=str(d.id),
                template=d.template,
                title=d.title,
                status=d.status,
                created_at=d.created_at,
            )
            for d in rows
        ]
    )


@router.get("/history", dependencies=[_USE])
async def history(
    conversation_id: str | None = Query(None),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
):
    if conversation_id:
        conv = await session.get(NirvanaConversation, UUID(conversation_id))
        if conv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
        msgs = await conversation_service.history(session, conversation_id)
        return ConversationDetail(
            conversation_id=str(conv.id),
            title=conv.title,
            module_context=conv.module_context,
            messages=[
                MessageOut(
                    id=str(m.id),
                    role=m.role,
                    content=m.content,
                    intent=m.intent,
                    grounded=m.grounded,
                    citations=m.citations,
                    model_used=m.model_used,
                    created_at=m.created_at,
                )
                for m in msgs
            ],
        )
    rows = (
        await session.scalars(
            select(NirvanaConversation).order_by(desc(NirvanaConversation.created_at))
        )
    ).all()
    return ConversationListResponse(
        conversations=[
            ConversationListItem(
                conversation_id=str(c.id),
                title=c.title,
                module_context=c.module_context,
                created_at=c.created_at,
            )
            for c in rows
        ]
    )
