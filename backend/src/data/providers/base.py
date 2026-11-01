"""Provider interfaces. Services depend on these, never on a concrete vendor (MD-04)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.core.domain.market import Bar, IndexQuote, NewsItem, Quote, ReferenceData, SymbolInfo
from src.data.resilience.circuit_breaker import BreakerState


class ProviderInfo(Protocol):
    name: str

    @property
    def configured(self) -> bool: ...

    @property
    def breaker_state(self) -> BreakerState: ...


class QuoteProvider(ProviderInfo, Protocol):
    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Quotes keyed by symbol. Unknown symbols are simply absent from the result."""
        ...


class BarsProvider(ProviderInfo, Protocol):
    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime | None = None
    ) -> list[Bar]: ...


class NewsProvider(ProviderInfo, Protocol):
    async def get_news(self, symbols: list[str], limit: int = 10) -> list[NewsItem]: ...


class SymbolListProvider(ProviderInfo, Protocol):
    async def list_symbols(self) -> list[SymbolInfo]:
        """Every active US stock and ETF the provider knows (MD-09)."""
        ...


class IndexQuoteProvider(ProviderInfo, Protocol):
    async def get_index_quote(self, index_id: str, name: str, symbol: str) -> IndexQuote: ...


class ReferenceDataProvider(ProviderInfo, Protocol):
    async def get_reference_data(self, symbol: str) -> ReferenceData: ...


# --- Roles the market service needs (implemented today by Alpaca / Alpha Vantage) ---


class LiveMarketProvider(QuoteProvider, BarsProvider, NewsProvider, SymbolListProvider, Protocol):
    """Real-time quotes, price bars, news and the symbol list."""


class ReferenceMarketProvider(IndexQuoteProvider, ReferenceDataProvider, Protocol):
    """Index quotes and security reference data."""
