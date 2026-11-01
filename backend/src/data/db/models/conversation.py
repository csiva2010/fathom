from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.data.db.base import Base, CreatedAtMixin, IdMixin, utcnow


class Conversation(IdMixin, CreatedAtMixin, Base):
    """Chat list entry. `id` doubles as the LangGraph thread_id."""

    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Feedback(IdMixin, CreatedAtMixin, Base):
    """Thumbs up/down on an answer (CH-08)."""

    __tablename__ = "feedback"

    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str] = mapped_column(String(64))
    rating: Mapped[int] = mapped_column(Integer)  # +1 / -1
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
