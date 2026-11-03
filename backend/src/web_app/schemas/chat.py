from __future__ import annotations

from datetime import datetime
from typing import Literal

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


class ImageAttachment(BaseModel):
    """A portfolio screenshot (CH-09). The route checks size and type; it is never stored."""

    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    data: str = Field(min_length=1, max_length=14_000_000, description="Base64 image bytes")


class MessageCreate(BaseModel):
    # The configured limit (workflow.max_message_chars) is checked by the route. Text may be
    # empty when an image is attached.
    content: str = Field(default="", max_length=20_000)
    image: ImageAttachment | None = None
