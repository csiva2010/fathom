from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.data.db.base import Base, CreatedAtMixin, IdMixin


class Goal(IdMixin, CreatedAtMixin, Base):
    """Goal-planning inputs (GL-02)."""

    __tablename__ = "goals"

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(32))  # retirement | house | emergency | other
    name: Mapped[str] = mapped_column(String(120), default="")
    target_amount: Mapped[float] = mapped_column(Float)
    target_date: Mapped[date] = mapped_column(Date)
    current_savings: Mapped[float] = mapped_column(Float, default=0)
    monthly_contribution: Mapped[float] = mapped_column(Float, default=0)
    risk_profile: Mapped[str] = mapped_column(String(16))
