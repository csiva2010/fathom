"""Market data service: the one place the API, agents and MCP ask for market data.

Callers ask for a data type, never a provider. Each method returns values stamped with
Freshness, and degrades to cached or mock data instead of failing (MD-04, OR-07).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.core.config.settings import CacheTtlConfig, IndexConfig, SectorEtfConfig
from src.core.domain.market import (
    DataStatus,
    IndexQuote,
    Indicators,
    NewsItem,
    PriceHistory,
    PriceRange,
    Quote,
    ReferenceData,
    SectorPerformance,
    Sourced,
    SymbolInfo,
)
from src.core.errors import ProviderBadResponse, ProviderError, UnknownSymbol, ValidationFailed
from src.core.logging import get_logger
from src.core.services.indicators import compute_indicators, rank_movers
from src.core.services.market.ranges import RANGE_SPECS, trim_to_sessions
from src.core.services.market.symbols import (
    MAX_QUERY_LENGTH,
    normalise_symbol,
    normalise_symbols,
    search_symbols,
    suggest_symbols,
)
from src.data.providers.base import LiveMarketProvider, ReferenceMarketProvider
from src.data.providers.chain import ProviderChain, Source
from src.data.providers.mock.provider import MockMarketProvider
from src.data.resilience.circuit_breaker import BreakerState

log = get_logger(__name__)


@dataclass
class QuoteBatch:
    quotes: list[Sourced[Quote]] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


@dataclass
class SymbolCheck:
    """Result of validating tickers against the symbol directory (MD-09).

    When only the local symbol table is available it cannot prove a ticker does not exist,
    so tickers missing from it are listed as `unverified` rather than `unknown`.
    """

    known: list[SymbolInfo] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    suggestions: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class MarketMovers:
    gainers: list[Sourced[Quote]] = field(default_factory=list)
    losers: list[Sourced[Quote]] = field(default_factory=list)


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
        sector_etfs: list[SectorEtfConfig] | None = None,
        movers_universe: list[str] | None = None,
    ):
        self._chain = chain
        self._alpaca = alpaca
        self._av = alpha_vantage
        self._mock = mock
        self._ttl = ttl
        self._indices = indices
        self._sector_etfs = sector_etfs or []
        self._movers_universe = movers_universe or []
        self._background: set[asyncio.Future[Any]] = set()

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

    async def get_reference_data(
        self, raw_symbol: str, *, timeout: float | None = None
    ) -> Sourced[ReferenceData]:
        """Reference data for one symbol.

        With `timeout`, a slow provider (Alpha Vantage queues behind a few requests per
        minute) does not hold the caller up: it gets stale cache or seed data now, and the
        provider call keeps running in the background to fill the cache for next time.
        """
        symbol = normalise_symbol(raw_symbol)
        lookup = self._chain.resolve(
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
        if timeout is None:
            return await lookup

        task = asyncio.ensure_future(lookup)
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout)
        except TimeoutError:
            self._background.add(task)
            task.add_done_callback(self._finish_background)
            log.info("reference data still loading, using fallback", extra={"symbol": symbol})
            stale = self._chain.cached_any(f"ref:{symbol}")
            return (
                stale if stale is not None else self._chain.mock(self._mock.reference_data(symbol))
            )

    def _finish_background(self, task: asyncio.Future[Any]) -> None:
        self._background.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.warning(
                "background reference lookup failed", extra={"error": str(task.exception())}
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

    # --- Symbol search and validation (MD-09) --------------------------------

    async def _symbol_directory(self) -> Sourced[list[SymbolInfo]]:
        return await self._chain.resolve(
            "symbols:us",
            self._ttl.symbols,
            [Source(self._alpaca.name, self._alpaca.list_symbols, self._alpaca.configured)],
            fallback=self._mock.symbol_table,
        )

    async def search_symbols(self, query: str, limit: int = 10) -> Sourced[list[SymbolInfo]]:
        query = query.strip()
        if not query:
            raise ValidationFailed("Type part of a ticker or company name to search.")
        if len(query) > MAX_QUERY_LENGTH:
            raise ValidationFailed(f"Search for at most {MAX_QUERY_LENGTH} characters.")
        directory = await self._symbol_directory()
        matches = search_symbols(directory.value, query, max(1, min(limit, 50)))
        return Sourced(value=matches, freshness=directory.freshness)

    async def validate_symbols(self, raw_symbols: list[str] | str) -> SymbolCheck:
        symbols = normalise_symbols(raw_symbols)
        directory = await self._symbol_directory()
        by_symbol = {entry.symbol: entry for entry in directory.value}
        authoritative = directory.freshness.status is not DataStatus.MOCK

        check = SymbolCheck()
        for symbol in symbols:
            if symbol in by_symbol:
                check.known.append(by_symbol[symbol])
            elif authoritative:
                check.unknown.append(symbol)
                check.suggestions[symbol] = suggest_symbols(list(by_symbol), symbol)
            else:
                check.unverified.append(symbol)
                check.known.append(SymbolInfo(symbol=symbol))
        return check

    async def validate_symbol(self, raw_symbol: str) -> SymbolInfo:
        check = await self.validate_symbols([raw_symbol])
        if check.unknown:
            symbol = check.unknown[0]
            raise UnknownSymbol([symbol], check.suggestions.get(symbol))
        return check.known[0]

    # --- Insights (MD-08) ----------------------------------------------------

    async def get_indicators(self, raw_symbol: str) -> Sourced[Indicators]:
        """Moving averages, 52-week range and volatility from a year of daily bars."""
        history = await self.get_history(raw_symbol, PriceRange.Y1)
        if not history.value.bars:
            raise UnknownSymbol([history.value.symbol])
        return Sourced(
            value=compute_indicators(history.value.symbol, history.value.bars),
            freshness=history.freshness,
        )

    async def get_movers(self, limit: int = 5) -> MarketMovers:
        """Biggest gainers and losers of the day from a fixed universe of liquid names."""
        if not self._movers_universe:
            return MarketMovers()
        batch = await self.get_quotes(self._movers_universe)
        gainers, losers = rank_movers(
            batch.quotes, lambda q: q.value.change_percent, max(1, min(limit, 20))
        )
        return MarketMovers(gainers=gainers, losers=losers)

    async def get_sector_performance(self) -> list[Sourced[SectorPerformance]]:
        """Each sector's day move through its sector ETF, best first."""
        if not self._sector_etfs:
            return []
        batch = await self.get_quotes([etf.symbol for etf in self._sector_etfs])
        quotes = {q.value.symbol: q for q in batch.quotes}
        sectors: list[Sourced[SectorPerformance]] = [
            Sourced(
                value=SectorPerformance(
                    sector=etf.sector,
                    symbol=etf.symbol,
                    price=quote.value.price,
                    change_percent=quote.value.change_percent,
                ),
                freshness=quote.freshness,
            )
            for etf in self._sector_etfs
            if (quote := quotes.get(etf.symbol)) is not None
        ]
        return sorted(
            sectors,
            key=lambda s: (s.value.change_percent is None, -(s.value.change_percent or 0)),
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
