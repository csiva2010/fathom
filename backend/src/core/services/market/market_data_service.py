"""Market data service: the one place the API, agents and MCP ask for market data.

Callers ask for a data type, never a provider. Each method returns values stamped with
Freshness, and degrades to cached or mock data instead of failing (MD-04, OR-07).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.core.config.settings import CacheTtlConfig, IndexConfig
from src.core.domain.market import (
    IndexQuote,
    NewsItem,
    PriceHistory,
    PriceRange,
    Quote,
    ReferenceData,
    Sourced,
)
from src.core.errors import ProviderBadResponse, ProviderError, UnknownSymbol
from src.core.logging import get_logger
from src.core.services.market.ranges import RANGE_SPECS, trim_to_sessions
from src.core.services.market.symbols import normalise_symbol, normalise_symbols
from src.data.providers.base import LiveMarketProvider, ReferenceMarketProvider
from src.data.providers.chain import ProviderChain, Source
from src.data.providers.mock.provider import MockMarketProvider
from src.data.resilience.circuit_breaker import BreakerState

log = get_logger(__name__)


@dataclass
class QuoteBatch:
    quotes: list[Sourced[Quote]] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    configured: bool
    breaker_state: BreakerState


class MarketDataService:
    def __init__(
        self,
        *,
        chain: ProviderChain,
        alpaca: LiveMarketProvider,
        alpha_vantage: ReferenceMarketProvider,
        mock: MockMarketProvider,
        ttl: CacheTtlConfig,
        indices: list[IndexConfig],
    ):
        self._chain = chain
        self._alpaca = alpaca
        self._av = alpha_vantage
        self._mock = mock
        self._ttl = ttl
        self._indices = indices

    # --- Quotes (MD-01) ------------------------------------------------------

    async def get_quotes(self, raw_symbols: list[str] | str) -> QuoteBatch:
        symbols = normalise_symbols(raw_symbols)
        found: dict[str, Sourced[Quote]] = {}
        missing: list[str] = []

        for symbol in symbols:
            cached = self._chain.cached_fresh(f"quote:{symbol}")
            if cached is not None:
                found[symbol] = cached
            else:
                missing.append(symbol)

        unknown: list[str] = []
        if missing and self._alpaca.configured:
            try:
                fetched = await self._alpaca.get_quotes(missing)
            except ProviderError:
                log.warning("live quotes unavailable, degrading", extra={"symbols": missing})
            else:
                for symbol, quote in fetched.items():
                    found[symbol] = self._chain.store(
                        f"quote:{symbol}", quote, self._alpaca.name, self._ttl.quote
                    )
                unknown = [s for s in missing if s not in fetched]
                missing = []

        for symbol in missing:
            stale = self._chain.cached_any(f"quote:{symbol}")
            if stale is not None:
                found[symbol] = stale
            elif self._mock.has_symbol(symbol):
                found[symbol] = self._chain.mock(self._mock.quote(symbol))
            else:
                unknown.append(symbol)

        return QuoteBatch(
            quotes=[found[s] for s in symbols if s in found],
            unknown=unknown,
        )

    async def get_quote(self, symbol: str) -> Sourced[Quote]:
        batch = await self.get_quotes([symbol])
        if not batch.quotes:
            raise UnknownSymbol(batch.unknown or [symbol])
        return batch.quotes[0]

    # --- Price history (MD-02) -----------------------------------------------

    async def get_history(self, raw_symbol: str, price_range: PriceRange) -> Sourced[PriceHistory]:
        symbol = normalise_symbol(raw_symbol)
        spec = RANGE_SPECS[price_range]
        start = datetime.now(UTC) - spec.lookback
        ttl = self._ttl.bars_intraday if spec.intraday else self._ttl.bars_daily

        async def from_alpaca() -> PriceHistory:
            bars = await self._alpaca.get_bars(symbol, spec.timeframe, start)
            if not bars:
                raise UnknownSymbol([symbol])
            return PriceHistory(
                symbol=symbol,
                range=price_range.value,
                timeframe=spec.timeframe,
                bars=trim_to_sessions(bars, spec.keep_sessions),
            )

        def from_mock() -> PriceHistory:
            bars = self._mock.bars(symbol, spec.timeframe, start)
            return PriceHistory(
                symbol=symbol,
                range=price_range.value,
                timeframe=spec.timeframe,
                bars=trim_to_sessions(bars, spec.keep_sessions),
            )

        return await self._chain.resolve(
            f"bars:{symbol}:{price_range.value}",
            ttl,
            [Source(self._alpaca.name, from_alpaca, self._alpaca.configured)],
            fallback=from_mock if self._mock.has_symbol(symbol) else None,
        )

    # --- Indices (MD-03) -----------------------------------------------------

    async def get_indices(self) -> list[Sourced[IndexQuote]]:
        return list(await asyncio.gather(*(self._get_index(index) for index in self._indices)))

    async def _get_index(self, index: IndexConfig) -> Sourced[IndexQuote]:
        async def from_alpha_vantage() -> IndexQuote:
            return await self._av.get_index_quote(index.id, index.name, index.av_symbol)

        async def from_etf_proxy() -> IndexQuote:
            quotes = await self._alpaca.get_quotes([index.proxy_symbol])
            quote = quotes.get(index.proxy_symbol)
            if quote is None:
                raise ProviderBadResponse(self._alpaca.name, f"no quote for {index.proxy_symbol}")
            return _proxy_index(index, quote)

        def from_mock() -> IndexQuote:
            return _proxy_index(index, self._mock.quote(index.proxy_symbol))

        return await self._chain.resolve(
            f"index:{index.id}",
            self._ttl.index,
            [
                Source(self._av.name, from_alpha_vantage, self._av.configured),
                Source(self._alpaca.name, from_etf_proxy, self._alpaca.configured),
            ],
            fallback=from_mock,
        )

    # --- Reference data (MD-03) ----------------------------------------------

    async def get_reference_data(self, raw_symbol: str) -> Sourced[ReferenceData]:
        symbol = normalise_symbol(raw_symbol)
        return await self._chain.resolve(
            f"ref:{symbol}",
            self._ttl.reference,
            [
                Source(
                    self._av.name,
                    lambda: self._av.get_reference_data(symbol),
                    self._av.configured,
                )
            ],
            fallback=lambda: self._mock.reference_data(symbol),
        )

    # --- News (MD-10) --------------------------------------------------------

    async def get_news(
        self, raw_symbols: list[str] | str | None = None, limit: int = 10
    ) -> Sourced[list[NewsItem]]:
        symbols = normalise_symbols(raw_symbols) if raw_symbols else []
        limit = max(1, min(limit, 50))
        return await self._chain.resolve(
            f"news:{','.join(sorted(symbols)) or 'market'}:{limit}",
            self._ttl.news,
            [
                Source(
                    self._alpaca.name,
                    lambda: self._alpaca.get_news(symbols, limit),
                    self._alpaca.configured,
                )
            ],
            fallback=list,  # empty state, never invented headlines
        )

    # --- Status (/health) ----------------------------------------------------

    def provider_status(self) -> list[ProviderStatus]:
        return [
            ProviderStatus(p.name, p.configured, p.breaker_state) for p in (self._alpaca, self._av)
        ]


def _proxy_index(index: IndexConfig, quote: Quote) -> IndexQuote:
    return IndexQuote(
        id=index.id,
        name=index.name,
        symbol=quote.symbol,
        is_proxy=True,
        price=quote.price,
        change=quote.change,
        change_percent=quote.change_percent,
        as_of=quote.as_of,
    )
