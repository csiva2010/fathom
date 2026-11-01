from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.workflow.streaming import ChatMessage


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    conversations: list[ConversationOut]


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[ChatMessage]


class MessageCreate(BaseModel):
    # The configured limit (workflow.max_message_chars) is checked by the route.
    content: str = Field(min_length=1, max_length=20_000)
