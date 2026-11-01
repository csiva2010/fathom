"""Pre-warm the market-data cache for the sample-portfolio tickers (MD-05).

The cache is in-process, so warming runs inside the API process at startup, in the
background, when `market.warm_cache.on_startup` is true. Failures are logged, never raised.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.core.logging import get_logger
from src.core.services.market.market_data_service import MarketDataService
from src.core.services.market.symbols import MAX_SYMBOLS
from src.data.providers.mock.seed_loader import SeedData

log = get_logger(__name__)


def sample_symbols(seed: SeedData, extra: Iterable[str] = ()) -> list[str]:
    symbols = {h["symbol"] for p in seed.sample_portfolios for h in p["holdings"]}
    return sorted(symbols | set(extra))


async def warm_cache(market: MarketDataService, symbols: list[str]) -> dict[str, int]:
    """Load indices, quotes, the symbol directory and reference data. Returns counts."""
    batch = symbols[:MAX_SYMBOLS]
    warmed = {"indices": 0, "quotes": 0, "symbols": 0, "reference": 0}

    async def indices() -> int:
        return len(await market.get_indices())

    async def quotes() -> int:
        return len((await market.get_quotes(batch)).quotes)

    async def directory() -> int:
        return len((await market.validate_symbols(batch)).known)

    for name, step in (("indices", indices), ("quotes", quotes), ("symbols", directory)):
        try:
            warmed[name] = await step()
        except Exception:  # warming is best effort
            log.exception("cache warm-up step failed", extra={"step": name})

    for symbol in symbols:  # sequential: Alpha Vantage allows only a few calls a minute
        try:
            await market.get_reference_data(symbol)
            warmed["reference"] += 1
        except Exception:
            log.exception(
                "cache warm-up step failed", extra={"step": "reference", "symbol": symbol}
            )
    log.info("cache warmed", extra=warmed)
    return warmed
