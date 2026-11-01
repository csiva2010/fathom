"""Portfolios (PF-01 to PF-07): build, import, save and analyze holdings.

Users see their own portfolios and the read-only samples. The analysis comes from
`PortfolioAnalysisService`, the same service the Portfolio agent uses, so the view and
chat agree. The most recently saved portfolio is what the agents load (PF-07).
`POST /portfolios/analyze` analyzes holdings without saving them, for the MCP
analyze_portfolio tool (MCP-01).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from src.core.domain.market import AssetClass, PriceRange
from src.core.domain.portfolio import HoldingInput as AnalysisHolding
from src.core.domain.portfolio import PortfolioAnalysis
from src.core.domain.risk import RiskProfile
from src.core.errors import ValidationFailed
from src.core.services.market.symbols import normalise_symbol
from src.data.db.models import Holding, Portfolio
from src.data.db.repositories.portfolio_repository import HoldingInput, PortfolioRepository
from src.data.db.repositories.user_repository import ProfileRepository
from src.utils.holdings_csv import parse_holdings_csv
from src.web_app.auth.current_user import CurrentUser, CurrentUserDep
from src.web_app.dependencies import DbDep, MarketDep, PortfoliosDep
from src.web_app.schemas.portfolios import (
    AnalyzeHoldingsIn,
    CsvImportIn,
    CsvImportOut,
    HoldingIn,
    HoldingOut,
    PortfolioIn,
    PortfolioList,
    PortfolioOut,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])

ASSET_CLASSES = set(AssetClass.__members__.values())


def _out(portfolio: Portfolio) -> PortfolioOut:
    return PortfolioOut(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        is_sample=portfolio.is_sample,
        created_at=portfolio.created_at,
        holdings=[
            HoldingOut(
                symbol=h.symbol,
                quantity=h.quantity,
                cost_basis=h.cost_basis,
                asset_class=AssetClass(h.asset_class) if h.asset_class in ASSET_CLASSES else None,
            )
            for h in portfolio.holdings
        ],
    )


async def _validated(rows: list[HoldingIn], market: MarketDep) -> list[HoldingInput]:
    """Normalised holdings; unknown tickers are rejected with suggestions (MD-09)."""
    holdings = [
        HoldingInput(
            symbol=normalise_symbol(h.symbol),
            quantity=h.quantity,
            cost_basis=h.cost_basis,
            asset_class=h.asset_class.value if h.asset_class else None,
        )
        for h in rows
    ]
    check = await market.validate_symbols(list(dict.fromkeys(h.symbol for h in holdings)))
    if check.unknown:
        hints = [
            f"{s} (did you mean {' or '.join(check.suggestions[s])}?)"
            if check.suggestions.get(s)
            else s
            for s in check.unknown
        ]
        raise ValidationFailed(f"We couldn't find {', '.join(hints)}. US stocks and ETFs only.")
    return holdings


@router.get("", response_model=PortfolioList, summary="Your portfolios, then the samples")
def list_portfolios(user: CurrentUserDep, db: DbDep) -> PortfolioList:
    return PortfolioList(
        portfolios=[_out(p) for p in PortfolioRepository(db).list_visible(user.id)]
    )


@router.post(
    "", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED, summary="Save a portfolio"
)
async def create_portfolio(
    body: PortfolioIn, user: CurrentUserDep, db: DbDep, market: MarketDep
) -> PortfolioOut:
    holdings = await _validated(body.holdings, market)
    portfolio = PortfolioRepository(db).create(
        user.id, body.name.strip(), body.description.strip(), holdings
    )
    db.commit()
    return _out(portfolio)


@router.post("/import", response_model=CsvImportOut, summary="Parse a holdings CSV for review")
def import_csv(body: CsvImportIn, _user: CurrentUserDep) -> CsvImportOut:
    parsed = parse_holdings_csv(body.content)
    return CsvImportOut(
        holdings=[
            HoldingIn(
                symbol=h.symbol,
                quantity=h.quantity,
                cost_basis=h.cost_basis,
                asset_class=AssetClass(h.asset_class) if h.asset_class else None,
            )
            for h in parsed.holdings
        ],
        errors=parsed.errors,
    )


@router.post(
    "/analyze",
    response_model=PortfolioAnalysis,
    summary="Analyze holdings without saving them",
)
async def analyze_holdings(
    body: AnalyzeHoldingsIn,
    user: CurrentUserDep,
    db: DbDep,
    market: MarketDep,
    portfolios: PortfoliosDep,
) -> PortfolioAnalysis:
    holdings = await _validated(body.holdings, market)
    return await _analyze(holdings, user, db, portfolios, body.range)


@router.get("/{portfolio_id}", response_model=PortfolioOut, summary="One portfolio")
def get_portfolio(portfolio_id: str, user: CurrentUserDep, db: DbDep) -> PortfolioOut:
    return _out(PortfolioRepository(db).get_visible(user.id, portfolio_id))


@router.put(
    "/{portfolio_id}", response_model=PortfolioOut, summary="Replace a portfolio's holdings"
)
async def update_portfolio(
    portfolio_id: str, body: PortfolioIn, user: CurrentUserDep, db: DbDep, market: MarketDep
) -> PortfolioOut:
    repo = PortfolioRepository(db)
    portfolio = repo.get_owned(user.id, portfolio_id)
    holdings = await _validated(body.holdings, market)
    repo.replace(portfolio, body.name.strip(), body.description.strip(), holdings)
    db.commit()
    return _out(portfolio)


@router.delete(
    "/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a portfolio"
)
def delete_portfolio(portfolio_id: str, user: CurrentUserDep, db: DbDep) -> Response:
    repo = PortfolioRepository(db)
    repo.delete(repo.get_owned(user.id, portfolio_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{portfolio_id}/analysis",
    response_model=PortfolioAnalysis,
    summary="Metrics, allocation, risk, benchmark and observations",
)
async def analyze_portfolio(
    portfolio_id: str,
    user: CurrentUserDep,
    db: DbDep,
    portfolios: PortfoliosDep,
    range_: Annotated[
        PriceRange, Query(alias="range", description="Benchmark window")
    ] = PriceRange.Y1,
) -> PortfolioAnalysis:
    portfolio = PortfolioRepository(db).get_visible(user.id, portfolio_id)
    return await _analyze(portfolio.holdings, user, db, portfolios, range_)


async def _analyze(
    rows: Sequence[HoldingInput | Holding],
    user: CurrentUser,
    db: DbDep,
    portfolios: PortfoliosDep,
    range_: PriceRange,
) -> PortfolioAnalysis:
    saved = ProfileRepository(db).get_or_create(user.id).risk_profile
    holdings = [
        AnalysisHolding(
            symbol=h.symbol,
            quantity=h.quantity,
            cost_basis=h.cost_basis,
            asset_class=AssetClass(h.asset_class) if h.asset_class in ASSET_CLASSES else None,
        )
        for h in rows
    ]
    return await portfolios.analyze(
        holdings, risk_profile=RiskProfile(saved) if saved else None, benchmark_range=range_
    )
