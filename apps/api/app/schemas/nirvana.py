"""Phase 6 — NirvanaI request/response schemas (§6)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    module_context: str | None = None


class Citation(BaseModel):
    type: str
    record_id: str
    label: str
    figure: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    intent: str
    grounded: bool
    citations: list[Citation]
    latency_ms: int | None = None


class DocContext(BaseModel):
    type: Literal["opportunity", "contract", "vendor"]
    id: str


class GenerateDocRequest(BaseModel):
    template: str
    context: DocContext
    conversation_id: str | None = None


class DocDraftResponse(BaseModel):
    draft_id: str
    template: str
    title: str
    body_markdown: str
    citations: list[Citation]
    status: str
    editable: bool = True


class DraftPatch(BaseModel):
    body_markdown: str | None = None
    title: str | None = None
    status: Literal["edited", "sent", "discarded"] | None = None


class DraftListItem(BaseModel):
    draft_id: str
    template: str
    title: str
    status: str
    created_at: datetime


class DraftListResponse(BaseModel):
    drafts: list[DraftListItem]


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    intent: str | None = None
    grounded: bool | None = None
    citations: list[dict] = []
    model_used: str | None = None
    created_at: datetime


class ConversationDetail(BaseModel):
    conversation_id: str
    title: str | None
    module_context: str | None
    messages: list[MessageOut]


class ConversationListItem(BaseModel):
    conversation_id: str
    title: str | None
    module_context: str | None
    created_at: datetime


class ConversationListResponse(BaseModel):
    conversations: list[ConversationListItem]
