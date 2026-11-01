from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.core.config import resolve_path
from src.core.config.settings import CacheTtlConfig, IndexConfig
from src.core.domain.market import (
    Bar,
    DataStatus,
    IndexQuote,
    NewsItem,
    PriceRange,
    Quote,
    ReferenceData,
)
from src.core.errors import ProviderUnavailable, UnknownSymbol, ValidationFailed
from src.core.services.market.market_data_service import MarketDataService
from src.data.cache.ttl_cache import TTLCache
from src.data.providers.chain import ProviderChain
from src.data.providers.mock.provider import MockMarketProvider
from src.data.providers.mock.seed_loader import SeedData
from src.data.resilience.circuit_breaker import BreakerState

NOW = datetime(2026, 10, 30, 15, 0, tzinfo=UTC)
INDICES = [IndexConfig(id="SPX", name="S&P 500", av_symbol="SPX", proxy_symbol="SPY")]


def quote(symbol: str, price: float = 10.0) -> Quote:
    return Quote(symbol=symbol, price=price, as_of=NOW)


class FakeAlpaca:
    name = "alpaca"
    breaker_state = BreakerState.CLOSED

    def __init__(self, configured: bool = True, known: set[str] | None = None) -> None:
        self.configured = configured
        self.known = known if known is not None else {"AAPL", "VOO", "SPY"}
        self.down = False
        self.quote_calls: list[list[str]] = []

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        self.quote_calls.append(symbols)
        if self.down:
            raise ProviderUnavailable(self.name, "down")
        return {s: quote(s) for s in symbols if s in self.known}

    async def get_bars(self, symbol: str, timeframe: str, start: datetime, end=None) -> list[Bar]:  # type: ignore[no-untyped-def]
        if self.down:
            raise ProviderUnavailable(self.name, "down")
        if symbol not in self.known:
            return []
        day = NOW - timedelta(days=1)
        return [
            Bar(t=day + timedelta(minutes=5 * i), open=1, high=1, low=1, close=1, volume=1)
            for i in range(3)
        ] + [Bar(t=NOW, open=1, high=1, low=1, close=1, volume=1)]

    async def get_news(self, symbols: list[str], limit: int = 10) -> list[NewsItem]:
        if self.down:
            raise ProviderUnavailable(self.name, "down")
        return [NewsItem(id="1", headline="h", published_at=NOW, symbols=symbols)]


class FakeAlphaVantage:
    name = "alpha_vantage"
    breaker_state = BreakerState.CLOSED

    def __init__(self, configured: bool = True) -> None:
        self.configured = configured
        self.down = False

    async def get_index_quote(self, index_id: str, name: str, symbol: str) -> IndexQuote:
        if self.down:
            raise ProviderUnavailable(self.name, "down")
        return IndexQuote(
            id=index_id, name=name, symbol=symbol, is_proxy=False, price=5800, as_of=NOW
        )

    async def get_reference_data(self, symbol: str) -> ReferenceData:
        if self.down:
            raise ProviderUnavailable(self.name, "down")
        return ReferenceData(symbol=symbol, name="Live name")


def make_service(alpaca: FakeAlpaca | None = None, av: FakeAlphaVantage | None = None):  # type: ignore[no-untyped-def]
    alpaca = alpaca or FakeAlpaca()
    av = av or FakeAlphaVantage()
    service = MarketDataService(
        chain=ProviderChain(TTLCache()),
        alpaca=alpaca,  # type: ignore[arg-type]
        alpha_vantage=av,  # type: ignore[arg-type]
        mock=MockMarketProvider(SeedData(resolve_path("data/seed")), now=NOW),
        ttl=CacheTtlConfig(),
        indices=INDICES,
    )
    return service, alpaca, av


# --- Quotes ------------------------------------------------------------------


async def test_quotes_live_then_cached_without_refetch() -> None:
    service, alpaca, _ = make_service()
    first = await service.get_quotes("aapl, VOO")
    assert [q.value.symbol for q in first.quotes] == ["AAPL", "VOO"]
    assert all(q.freshness.status is DataStatus.LIVE for q in first.quotes)

    second = await service.get_quotes(["AAPL"])
    assert second.quotes[0].freshness.status is DataStatus.CACHED
    assert len(alpaca.quote_calls) == 1


async def test_unknown_symbols_are_reported_not_mocked() -> None:
    service, _, _ = make_service()
    batch = await service.get_quotes(["AAPL", "ZZZZ"])
    assert batch.unknown == ["ZZZZ"]
    with pytest.raises(UnknownSymbol):
        await service.get_quote("ZZZZ")


async def test_quotes_degrade_to_stale_then_mock_when_provider_down() -> None:
    service, alpaca, _ = make_service()
    await service.get_quotes(["AAPL"])
    # Expire the cached quote, then take the provider down.
    entry = service._chain.cache.get_any("quote:AAPL")
    assert entry is not None
    entry.expires_at = 0
    alpaca.down = True

    batch = await service.get_quotes(["AAPL", "VOO", "NOPE"])
    statuses = {q.value.symbol: q.freshness.status for q in batch.quotes}
    assert statuses == {"AAPL": DataStatus.CACHED, "VOO": DataStatus.MOCK}
    assert batch.unknown == ["NOPE"]


async def test_quotes_use_mock_when_alpaca_not_configured() -> None:
    service, alpaca, _ = make_service(alpaca=FakeAlpaca(configured=False))
    single = await service.get_quote("VOO")
    assert single.freshness.status is DataStatus.MOCK
    assert alpaca.quote_calls == []


async def test_invalid_symbols_rejected() -> None:
    service, _, _ = make_service()
    with pytest.raises(ValidationFailed):
        await service.get_quotes("AAPL,$$$")


# --- History -----------------------------------------------------------------


async def test_history_live_is_trimmed_to_sessions() -> None:
    service, _, _ = make_service()
    result = await service.get_history("aapl", PriceRange.D1)
    assert result.freshness.status is DataStatus.LIVE
    assert len(result.value.bars) == 1  # only the most recent session is kept
    assert result.value.timeframe == "5Min"


async def test_history_unknown_symbol_and_mock_fallback() -> None:
    service, alpaca, _ = make_service()
    with pytest.raises(UnknownSymbol):
        await service.get_history("ZZZZ", PriceRange.M1)

    alpaca.down = True
    result = await service.get_history("VOO", PriceRange.Y1)
    assert result.freshness.status is DataStatus.MOCK
    assert result.value.bars


# --- Indices -----------------------------------------------------------------


async def test_indices_prefer_alpha_vantage() -> None:
    service, _, _ = make_service()
    [spx] = await service.get_indices()
    assert spx.value.is_proxy is False
    assert spx.freshness.source == "alpha_vantage"


async def test_indices_fall_back_to_etf_proxy_then_mock() -> None:
    av = FakeAlphaVantage()
    av.down = True
    service, _, _ = make_service(av=av)
    [spx] = await service.get_indices()
    assert spx.value.is_proxy is True
    assert spx.value.symbol == "SPY"
    assert spx.freshness.source == "alpaca"

    service2, _, _ = make_service(alpaca=FakeAlpaca(known=set()), av=av)
    [mocked] = await service2.get_indices()
    assert mocked.freshness.status is DataStatus.MOCK
    assert mocked.value.is_proxy is True


# --- Reference data and news -------------------------------------------------


async def test_reference_data_live_and_seed_fallback() -> None:
    service, _, av = make_service()
    assert (await service.get_reference_data("AAPL")).value.name == "Live name"
    av.down = True
    fallback = await service.get_reference_data("VOO")
    assert fallback.freshness.status is DataStatus.MOCK
    assert fallback.value.expense_ratio == 0.0003


async def test_news_live_and_empty_fallback() -> None:
    service, alpaca, _ = make_service()
    live = await service.get_news("AAPL", limit=500)
    assert live.value[0].symbols == ["AAPL"]
    alpaca.down = True
    empty = await service.get_news(None)
    assert empty.value == []
    assert empty.freshness.status is DataStatus.MOCK


def test_provider_status() -> None:
    service, _, _ = make_service(av=FakeAlphaVantage(configured=False))
    status = {s.name: s.configured for s in service.provider_status()}
    assert status == {"alpaca": True, "alpha_vantage": False}
