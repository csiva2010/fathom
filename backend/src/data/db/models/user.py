from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.db.base import Base, CreatedAtMixin, IdMixin

if TYPE_CHECKING:
    from src.data.db.models.profile import Profile


class User(IdMixin, CreatedAtMixin, Base):
    """One row per Google account or guest (AU-03). Only ID, email, name, avatar are stored
    (NF-S03). Guests have a generated `google_sub` of the form "guest:<hex>" and no email."""

    __tablename__ = "users"

    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(255), default="")
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    profile: Mapped[Profile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
