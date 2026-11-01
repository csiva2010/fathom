"""Market data routes. Every number carries its freshness (MD-07)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from src.core.domain.market import PriceRange
from src.core.errors import UnknownSymbol
from src.web_app.auth.current_user import CurrentUserDep
from src.web_app.dependencies import MarketDep
from src.web_app.schemas.market import (
    HistoryResponse,
    IndexOut,
    IndicatorsResponse,
    MarketOverviewResponse,
    MoversResponse,
    NewsResponse,
    QuoteOut,
    QuotesResponse,
    SectorOut,
    SectorsResponse,
    SymbolSearchResponse,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/quotes", response_model=QuotesResponse, summary="Batch quotes with freshness")
async def get_quotes(
    _user: CurrentUserDep,
    market: MarketDep,
    symbols: Annotated[str, Query(description="Comma-separated tickers, e.g. AAPL,VOO")],
) -> QuotesResponse:
    batch = await market.get_quotes(symbols)
    if not batch.quotes:
        raise UnknownSymbol(batch.unknown)
    return QuotesResponse(
        quotes=[QuoteOut(quote=q.value, freshness=q.freshness) for q in batch.quotes],
        unknown_symbols=batch.unknown,
    )


@router.get("/history/{symbol}", response_model=HistoryResponse, summary="Price bars for charts")
async def get_history(
    symbol: str,
    _user: CurrentUserDep,
    market: MarketDep,
    range_: Annotated[PriceRange, Query(alias="range")] = PriceRange.M1,
) -> HistoryResponse:
    result = await market.get_history(symbol, range_)
    return HistoryResponse(history=result.value, freshness=result.freshness)


@router.get("/overview", response_model=MarketOverviewResponse, summary="Index cards")
async def get_overview(_user: CurrentUserDep, market: MarketDep) -> MarketOverviewResponse:
    indices = await market.get_indices()
    return MarketOverviewResponse(
        indices=[IndexOut(index=i.value, freshness=i.freshness) for i in indices]
    )


@router.get("/news", response_model=NewsResponse, summary="Ticker or market news")
async def get_news(
    _user: CurrentUserDep,
    market: MarketDep,
    symbols: Annotated[str | None, Query(description="Comma-separated tickers")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> NewsResponse:
    result = await market.get_news(symbols, limit)
    return NewsResponse(items=result.value, freshness=result.freshness)


@router.get("/movers", response_model=MoversResponse, summary="Today's biggest gainers and losers")
async def get_movers(
    _user: CurrentUserDep, market: MarketDep, limit: Annotated[int, Query(ge=1, le=20)] = 5
) -> MoversResponse:
    movers = await market.get_movers(limit)
    return MoversResponse(
        gainers=[QuoteOut(quote=q.value, freshness=q.freshness) for q in movers.gainers],
        losers=[QuoteOut(quote=q.value, freshness=q.freshness) for q in movers.losers],
    )


@router.get("/sectors", response_model=SectorsResponse, summary="Sector moves via sector ETFs")
async def get_sectors(_user: CurrentUserDep, market: MarketDep) -> SectorsResponse:
    sectors = await market.get_sector_performance()
    return SectorsResponse(
        sectors=[SectorOut(sector=s.value, freshness=s.freshness) for s in sectors]
    )


@router.get("/symbols", response_model=SymbolSearchResponse, summary="Ticker search (MD-09)")
async def search_symbols(
    _user: CurrentUserDep,
    market: MarketDep,
    q: Annotated[str, Query(min_length=1, max_length=50, description="Ticker or company name")],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SymbolSearchResponse:
    result = await market.search_symbols(q, limit)
    return SymbolSearchResponse(results=result.value, freshness=result.freshness)


@router.get(
    "/indicators/{symbol}",
    response_model=IndicatorsResponse,
    summary="Moving averages, 52-week range and volatility",
)
async def get_indicators(
    symbol: str, _user: CurrentUserDep, market: MarketDep
) -> IndicatorsResponse:
    result = await market.get_indicators(symbol)
    return IndicatorsResponse(indicators=result.value, freshness=result.freshness)
