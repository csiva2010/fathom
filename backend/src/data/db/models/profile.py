from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.db.base import Base

if TYPE_CHECKING:
    from src.data.db.models.user import User


class Profile(Base):
    """Onboarding results: experience level, risk profile, disclaimer acceptance (UI-02)."""

    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    experience_level: Mapped[str] = mapped_column(String(16), default="beginner")
    risk_profile: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_answers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    disclaimer_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="profile")
