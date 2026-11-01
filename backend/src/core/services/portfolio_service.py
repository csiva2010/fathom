"""Portfolio analysis service: gathers the market data the pure analytics need (PF-02 to PF-06).

The Portfolio view and the Portfolio agent both call this, so chat and screen show the
same numbers. Missing data degrades the analysis (fewer metrics), it never fails it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from src.core.domain.market import Bar, Freshness, PriceRange, Quote, ReferenceData, Sourced
from src.core.domain.portfolio import HoldingInput, PortfolioAnalysis
from src.core.domain.risk import RiskProfile
from src.core.errors import AppError
from src.core.logging import get_logger
from src.core.services.market.market_data_service import MarketDataService
from src.core.services.market.symbols import MAX_SYMBOLS, normalise_symbol
from src.core.services.portfolio_analytics import analyze, merge_holdings

log = get_logger(__name__)

# Reference data comes from a slow, low-quota provider; don't hold the analysis for it.
REFERENCE_TIMEOUT_SECONDS = 3.0


class PortfolioAnalysisService:
    def __init__(
        self,
        market: MarketDataService,
        *,
        benchmark_symbol: str = "SPY",
        reference_timeout: float = REFERENCE_TIMEOUT_SECONDS,
    ):
        self._market = market
        self._benchmark = benchmark_symbol
        self._reference_timeout = reference_timeout

    async def analyze(
        self,
        holdings: Sequence[HoldingInput],
        *,
        risk_profile: RiskProfile | None = None,
        benchmark_range: PriceRange = PriceRange.Y1,
    ) -> PortfolioAnalysis:
        merged = merge_holdings(
            h.model_copy(update={"symbol": normalise_symbol(h.symbol)}) for h in holdings
        )
        quotes = await self._quotes([h.symbol for h in merged])
        symbols = list(quotes)

        references, histories, benchmark = await asyncio.gather(
            asyncio.gather(*(self._reference(s) for s in symbols)),
            asyncio.gather(*(self._history(s, benchmark_range) for s in symbols)),
            self._history(self._benchmark, benchmark_range) if symbols else _none(),
        )

        reference = {s: r.value for s, r in zip(symbols, references, strict=True) if r}
        bars: dict[str, list[Bar]] = {
            s: h.value for s, h in zip(symbols, histories, strict=True) if h
        }
        analysis = analyze(
            merged,
            {s: q.value.price for s, q in quotes.items()},
            reference,
            bars,
            risk_profile=risk_profile,
            benchmark_bars=benchmark.value if benchmark else [],
            benchmark_symbol=self._benchmark,
            range_label=benchmark_range.value,
        )
        analysis.freshness = summarize_freshness(
            [q.freshness for q in quotes.values()]
            + [r.freshness for r in references if r]
            + [h.freshness for h in [*histories, benchmark] if h]
        )
        return analysis

    async def _quotes(self, symbols: list[str]) -> dict[str, Sourced[Quote]]:
        found: dict[str, Sourced[Quote]] = {}
        for start in range(0, len(symbols), MAX_SYMBOLS):
            batch = await self._market.get_quotes(symbols[start : start + MAX_SYMBOLS])
            found.update({q.value.symbol: q for q in batch.quotes})
        return found

    async def _reference(self, symbol: str) -> Sourced[ReferenceData] | None:
        try:
            return await self._market.get_reference_data(symbol, timeout=self._reference_timeout)
        except AppError as error:
            log.warning("reference data unavailable", extra={"symbol": symbol, "error": error.code})
            return None

    async def _history(self, symbol: str, price_range: PriceRange) -> Sourced[list[Bar]] | None:
        try:
            history = await self._market.get_history(symbol, price_range)
        except AppError as error:
            log.warning("price history unavailable", extra={"symbol": symbol, "error": error.code})
            return None
        return Sourced(value=history.value.bars, freshness=history.freshness)


async def _none() -> None:
    return None


def summarize_freshness(stamps: Sequence[Freshness]) -> list[Freshness]:
    """One stamp per (source, status), keeping the oldest time, so the badge stays honest."""
    oldest: dict[tuple[str, str], Freshness] = {}
    for stamp in stamps:
        key = (stamp.source, stamp.status.value)
        if key not in oldest or stamp.as_of < oldest[key].as_of:
            oldest[key] = stamp
    return sorted(oldest.values(), key=lambda f: (f.status.value, f.source))
