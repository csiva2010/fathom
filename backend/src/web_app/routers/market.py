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
    MarketOverviewResponse,
    NewsResponse,
    QuoteOut,
    QuotesResponse,
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
