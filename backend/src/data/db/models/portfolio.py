from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.db.base import Base, CreatedAtMixin, IdMixin


class Portfolio(IdMixin, CreatedAtMixin, Base):
    """User portfolios and the read-only preloaded samples (user_id is NULL for samples)."""

    __tablename__ = "portfolios"

    user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)

    holdings: Mapped[list[Holding]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan", order_by="Holding.symbol"
    )


class Holding(IdMixin, Base):
    __tablename__ = "holdings"

    portfolio_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float] = mapped_column(Float)
    cost_basis: Mapped[float | None] = mapped_column(Float, nullable=True)  # per share
    asset_class: Mapped[str | None] = mapped_column(String(16), nullable=True)

    portfolio: Mapped[Portfolio] = relationship(back_populates="holdings")
