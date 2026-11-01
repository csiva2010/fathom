"""Portfolio persistence. Day 1 only needs sample seeding; CRUD lands with the Portfolio view."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.data.db.models import Holding, Portfolio


@dataclass(frozen=True)
class HoldingInput:
    symbol: str
    quantity: float
    cost_basis: float | None = None
    asset_class: str | None = None


class PortfolioRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_samples(self) -> list[Portfolio]:
        stmt = (
            select(Portfolio)
            .where(Portfolio.is_sample.is_(True))
            .options(selectinload(Portfolio.holdings))
            .order_by(Portfolio.name)
        )
        return list(self._session.scalars(stmt))

    def upsert_sample(
        self, name: str, description: str, holdings: Iterable[HoldingInput]
    ) -> Portfolio:
        """Idempotent: re-running the seed replaces a sample's holdings instead of duplicating."""
        portfolio = self._session.scalar(
            select(Portfolio).where(Portfolio.is_sample.is_(True), Portfolio.name == name)
        )
        if portfolio is None:
            portfolio = Portfolio(name=name, is_sample=True, user_id=None)
            self._session.add(portfolio)
        portfolio.description = description
        portfolio.holdings = [
            Holding(
                symbol=h.symbol.upper(),
                quantity=h.quantity,
                cost_basis=h.cost_basis,
                asset_class=h.asset_class,
            )
            for h in holdings
        ]
        self._session.flush()
        return portfolio
