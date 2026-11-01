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


class SymbolInfo(BaseModel):
    """One entry in the symbol directory used for ticker search and validation (MD-09)."""

    symbol: str
    name: str = ""
    exchange: str = ""


class Indicators(BaseModel):
    """Plain-language market insights for one symbol, computed from daily bars (MD-08).

    Percent fields are percentages (1.5 means 1.5%).
    """

    symbol: str
    last_close: float
    as_of: datetime
    period_change_percent: float | None = None  # first to last bar of the window
    sma_50: float | None = None
    sma_200: float | None = None
    price_vs_sma_50_percent: float | None = None
    price_vs_sma_200_percent: float | None = None
    week52_low: float | None = None
    week52_high: float | None = None
    week52_position_percent: float | None = None  # 0 = at the low, 100 = at the high
    volatility_30d_percent: float | None = None  # annualized
    max_drawdown_percent: float | None = None  # worst peak-to-trough fall in the window
    bars_used: int = 0


class SectorPerformance(BaseModel):
    """A sector's day move, measured through its sector ETF (MD-08)."""

    sector: str
    symbol: str
    price: float
    change_percent: float | None = None
