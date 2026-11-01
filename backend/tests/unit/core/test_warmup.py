from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from src.core.config import resolve_path
from src.core.errors import ProviderUnavailable
from src.core.services.market.factory import build_market_service
from src.core.services.market.warmup import sample_symbols, warm_cache
from src.data.providers.mock.seed_loader import SeedData
from tests.conftest import make_settings


def test_sample_symbols_include_extras() -> None:
    symbols = sample_symbols(SeedData(resolve_path("data/seed")), ["SPY"])
    assert "SPY" in symbols and "AAPL" in symbols
    assert symbols == sorted(set(symbols))


async def test_warm_cache_fills_every_data_type(tmp_path: Path) -> None:
    async with httpx.AsyncClient() as client:
        market = build_market_service(make_settings(tmp_path), client)
        warmed = await warm_cache(market, ["AAPL", "VOO"])
    assert warmed == {"indices": 3, "quotes": 2, "symbols": 2, "reference": 2}


async def test_warm_cache_is_best_effort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(*args: object, **kwargs: object) -> None:
        raise ProviderUnavailable("alpaca", "down")

    async with httpx.AsyncClient() as client:
        market = build_market_service(make_settings(tmp_path), client)
        for name in ("get_indices", "get_quotes", "validate_symbols", "get_reference_data"):
            monkeypatch.setattr(market, name, fail)
        warmed = await warm_cache(market, ["AAPL"])
    assert warmed == {"indices": 0, "quotes": 0, "symbols": 0, "reference": 0}
