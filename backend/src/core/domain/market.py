"""Market data domain models shared by providers, services, API and (later) agents."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class DataStatus(StrEnum):
    LIVE = "live"
    CACHED = "cached"
    MOCK = "mock"


class Freshness(BaseModel):
    """Where a number came from and how fresh it is (MD-07). Shown as a badge in the UI."""

    source: str
    as_of: datetime
    status: DataStatus


class Sourced(BaseModel, Generic[T]):
    """A value plus its freshness stamp."""

    value: T
    freshness: Freshness


class Quote(BaseModel):
    symbol: str
    price: float
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    as_of: datetime


class Bar(BaseModel):
    t: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceHistory(BaseModel):
    symbol: str
    range: str
    timeframe: str
    bars: list[Bar]


class IndexQuote(BaseModel):
    id: str
    name: str
    symbol: str  # the symbol actually quoted (index or ETF proxy)
    is_proxy: bool
    price: float
    change: float | None = None
    change_percent: float | None = None
    as_of: datetime


class NewsItem(BaseModel):
    id: str
    headline: str
    summary: str = ""
    source: str = ""
    url: str = ""
    symbols: list[str] = Field(default_factory=list)
    published_at: datetime


class AssetClass(StrEnum):
    STOCK = "stock"
    ETF = "etf"
    BOND_ETF = "bond_etf"
    CASH = "cash"
    OTHER = "other"


class SectorWeight(BaseModel):
    sector: str
    weight: float


class ReferenceData(BaseModel):
    """Static-ish facts about a security (MD-03)."""

    symbol: str
    name: str = ""
    asset_class: AssetClass = AssetClass.OTHER
    sector: str | None = None
    industry: str | None = None
    beta: float | None = None
    expense_ratio: float | None = None  # ETFs only, as a fraction (0.0003 = 0.03%)
    sector_weights: list[SectorWeight] = Field(default_factory=list)


class PriceRange(StrEnum):
    D1 = "1D"
    D5 = "5D"
    M1 = "1M"
    M3 = "3M"
    M6 = "6M"
    Y1 = "1Y"
    Y5 = "5Y"
