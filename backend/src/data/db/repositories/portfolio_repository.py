"""Portfolio persistence (PF-01, PF-07).

Users see their own portfolios plus the read-only samples; only their own can change.
Every query is scoped by the owner's user id (AU-03).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from src.core.errors import Forbidden, NotFound
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
        portfolio.holdings = [_holding(h) for h in holdings]
        self._session.flush()
        return portfolio

    def list_visible(self, user_id: str) -> list[Portfolio]:
        """The user's portfolios (newest first), then the samples."""
        stmt = (
            select(Portfolio)
            .where(or_(Portfolio.user_id == user_id, Portfolio.is_sample.is_(True)))
            .options(selectinload(Portfolio.holdings))
            .order_by(Portfolio.is_sample, Portfolio.created_at.desc(), Portfolio.name)
        )
        return list(self._session.scalars(stmt))

    def get_visible(self, user_id: str, portfolio_id: str) -> Portfolio:
        portfolio = self._session.get(Portfolio, portfolio_id)
        if portfolio is None or not (portfolio.is_sample or portfolio.user_id == user_id):
            raise NotFound("That portfolio doesn't exist.")
        return portfolio

    def get_owned(self, user_id: str, portfolio_id: str) -> Portfolio:
        portfolio = self.get_visible(user_id, portfolio_id)
        if portfolio.is_sample:
            raise Forbidden("Sample portfolios can't be changed. Save a copy to edit it.")
        return portfolio

    def create(
        self, user_id: str, name: str, description: str, holdings: Iterable[HoldingInput]
    ) -> Portfolio:
        portfolio = Portfolio(user_id=user_id, name=name, description=description, is_sample=False)
        self._session.add(portfolio)
        self.replace(portfolio, name, description, holdings)
        return portfolio

    def replace(
        self, portfolio: Portfolio, name: str, description: str, holdings: Iterable[HoldingInput]
    ) -> Portfolio:
        portfolio.name = name
        portfolio.description = description
        portfolio.holdings = [_holding(h) for h in holdings]
        self._session.flush()
        return portfolio

    def delete(self, portfolio: Portfolio) -> None:
        self._session.delete(portfolio)
        self._session.flush()


def _holding(h: HoldingInput) -> Holding:
    return Holding(
        symbol=h.symbol.upper(),
        quantity=h.quantity,
        cost_basis=h.cost_basis,
        asset_class=h.asset_class,
    )
