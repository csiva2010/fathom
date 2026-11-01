"""Conversation list persistence (CH-07). Messages live in the LangGraph checkpoint.

Every lookup is scoped by the owner's user id (AU-03): another user's conversation is
reported as not found, never as forbidden, so ids can't be probed.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.errors import NotFound
from src.data.db.base import utcnow
from src.data.db.models import Conversation

DEFAULT_TITLE = "New conversation"
TITLE_CHARS = 60


def title_from(text: str) -> str:
    """A short title from the first message, cut at a word boundary."""
    words = " ".join(text.split())
    if len(words) <= TITLE_CHARS:
        return words or DEFAULT_TITLE
    cut = words[:TITLE_CHARS].rsplit(" ", 1)[0] or words[:TITLE_CHARS]
    return f"{cut}…"


class ConversationRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_for(self, user_id: str) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(self._session.scalars(stmt))

    def create(self, user_id: str, title: str | None = None) -> Conversation:
        conversation = Conversation(user_id=user_id, title=(title or "").strip() or DEFAULT_TITLE)
        self._session.add(conversation)
        self._session.flush()
        return conversation

    def get_owned(self, user_id: str, conversation_id: str) -> Conversation:
        conversation = self._session.get(Conversation, conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise NotFound("That conversation doesn't exist.")
        return conversation

    def record_turn(self, conversation: Conversation, text: str) -> None:
        """Bump the conversation to the top of the list; the first message names it."""
        if conversation.title == DEFAULT_TITLE:
            conversation.title = title_from(text)
        conversation.updated_at = utcnow()
        self._session.flush()

    def delete(self, conversation: Conversation) -> None:
        self._session.delete(conversation)
        self._session.flush()
