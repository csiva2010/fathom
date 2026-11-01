"""Deterministic mock provider: the last fallback for every data type (MD-04).

Values are generated from a seeded random walk so the same symbol always gives the same
series on the same day. Results are always labelled status=mock by the provider chain.
"""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta

from src.core.domain.market import (
    AssetClass,
    Bar,
    IndexQuote,
    NewsItem,
    Quote,
    ReferenceData,
    SymbolInfo,
)
from src.data.providers.mock.seed_loader import SeedData
from src.data.resilience.circuit_breaker import BreakerState

DEFAULT_PRICE = 100.0
TIMEFRAME_STEPS: dict[str, timedelta] = {
    "5Min": timedelta(minutes=5),
    "30Min": timedelta(minutes=30),
    "1Hour": timedelta(hours=1),
    "1Day": timedelta(days=1),
    "1Week": timedelta(weeks=1),
}


def _seed_for(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(digest[:12], 16)


class MockMarketProvider:
    name = "mock"
    configured = True
    breaker_state = BreakerState.CLOSED

    def __init__(self, seed: SeedData, *, now: datetime | None = None):
        self._seed = seed
        self._fixed_now = now

    def _now(self) -> datetime:
        return self._fixed_now or datetime.now(UTC)

    def _base_price(self, symbol: str) -> float:
        return self._seed.base_prices.get(symbol, DEFAULT_PRICE)

    def has_symbol(self, symbol: str) -> bool:
        return symbol in self._seed.base_prices

    # --- Quotes ------------------------------------------------------------

    def quote(self, symbol: str) -> Quote:
        now = self._now()
        rng = random.Random(_seed_for(symbol, now.date().isoformat()))
        previous_close = self._base_price(symbol)
        change_percent = rng.uniform(-2.0, 2.0)
        price = round(previous_close * (1 + change_percent / 100), 2)
        return Quote(
            symbol=symbol,
            price=price,
            previous_close=previous_close,
            change=round(price - previous_close, 2),
            change_percent=round(change_percent, 2),
            open=previous_close,
            high=max(price, previous_close),
            low=min(price, previous_close),
            volume=rng.randint(1_000_000, 50_000_000),
            as_of=now,
        )

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        return {s: self.quote(s) for s in symbols}

    # --- Bars --------------------------------------------------------------

    def bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime | None = None
    ) -> list[Bar]:
        step = TIMEFRAME_STEPS.get(timeframe, timedelta(days=1))
        end = end or self._now()
        rng = random.Random(_seed_for(symbol, timeframe, start.date().isoformat()))
        daily_vol = 0.012 if step >= timedelta(days=1) else 0.002

        # Walk backwards from today's base price so the series ends near the quote.
        count = max(1, min(5_000, int((end - start) / step)))
        closes = [self._base_price(symbol)]
        for _ in range(count - 1):
            closes.append(closes[-1] / (1 + rng.gauss(0.0003, daily_vol)))
        closes.reverse()

        bars: list[Bar] = []
        for i, close in enumerate(closes):
            open_ = close * (1 + rng.gauss(0, daily_vol / 2))
            bars.append(
                Bar(
                    t=start + step * i,
                    open=round(open_, 2),
                    high=round(max(open_, close) * (1 + abs(rng.gauss(0, daily_vol / 2))), 2),
                    low=round(min(open_, close) * (1 - abs(rng.gauss(0, daily_vol / 2))), 2),
                    close=round(close, 2),
                    volume=rng.randint(500_000, 20_000_000),
                )
            )
        return bars

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime | None = None
    ) -> list[Bar]:
        return self.bars(symbol, timeframe, start, end)

    # --- Indices -----------------------------------------------------------

    def index_quote(self, index_id: str, name: str, symbol: str) -> IndexQuote:
        quote = self.quote(symbol)
        return IndexQuote(
            id=index_id,
            name=name,
            symbol=symbol,
            is_proxy=False,
            price=quote.price,
            change=quote.change,
            change_percent=quote.change_percent,
            as_of=quote.as_of,
        )

    async def get_index_quote(self, index_id: str, name: str, symbol: str) -> IndexQuote:
        return self.index_quote(index_id, name, symbol)

    # --- News --------------------------------------------------------------

    async def get_news(self, symbols: list[str], limit: int = 10) -> list[NewsItem]:
        # Design: news falls back to an empty state, not invented headlines.
        return []

    # --- Reference data ----------------------------------------------------

    def reference_data(self, symbol: str) -> ReferenceData:
        return self._seed.reference.get(
            symbol, ReferenceData(symbol=symbol, asset_class=AssetClass.OTHER)
        )

    async def get_reference_data(self, symbol: str) -> ReferenceData:
        return self.reference_data(symbol)

    # --- Symbol table ------------------------------------------------------

    def symbol_table(self) -> list[SymbolInfo]:
        """The local symbol table: every symbol the seed files know about."""
        reference = self._seed.reference
        symbols = sorted({*self._seed.base_prices, *reference})
        return [
            SymbolInfo(symbol=s, name=reference[s].name if s in reference else "") for s in symbols
        ]

    async def list_symbols(self) -> list[SymbolInfo]:
        return self.symbol_table()
