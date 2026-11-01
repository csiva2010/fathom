from __future__ import annotations

from pydantic import BaseModel

from src.core.domain.market import (
    Freshness,
    IndexQuote,
    NewsItem,
    PriceHistory,
    Quote,
)


class QuoteOut(BaseModel):
    quote: Quote
    freshness: Freshness


class QuotesResponse(BaseModel):
    quotes: list[QuoteOut]
    unknown_symbols: list[str]


class IndexOut(BaseModel):
    index: IndexQuote
    freshness: Freshness


class MarketOverviewResponse(BaseModel):
    """Day 1: indices. Sector performance and movers arrive with the indicators service."""

    indices: list[IndexOut]


class HistoryResponse(BaseModel):
    history: PriceHistory
    freshness: Freshness


class NewsResponse(BaseModel):
    items: list[NewsItem]
    freshness: Freshness
