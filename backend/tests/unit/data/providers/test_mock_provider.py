from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.core.config import resolve_path
from src.core.domain.market import AssetClass
from src.data.providers.mock.provider import MockMarketProvider
from src.data.providers.mock.seed_loader import SeedData

NOW = datetime(2026, 10, 30, 16, 0, tzinfo=UTC)


def make_mock() -> MockMarketProvider:
    return MockMarketProvider(SeedData(resolve_path("data/seed")), now=NOW)


async def test_quotes_are_deterministic_per_day() -> None:
    mock = make_mock()
    first = await mock.get_quotes(["AAPL", "UNKNOWN"])
    second = await mock.get_quotes(["AAPL"])
    assert first["AAPL"] == second["AAPL"]
    assert first["UNKNOWN"].previous_close == 100.0
    assert mock.has_symbol("AAPL")
    assert not mock.has_symbol("UNKNOWN")


async def test_bars_cover_the_window_and_end_at_base_price() -> None:
    mock = make_mock()
    bars = await mock.get_bars("VOO", "1Day", NOW - timedelta(days=30), NOW)
    assert 25 <= len(bars) <= 31
    assert bars[-1].close == 529.3
    assert all(b.low <= min(b.open, b.close) and b.high >= max(b.open, b.close) for b in bars)


async def test_index_news_and_reference() -> None:
    mock = make_mock()
    index = await mock.get_index_quote("SPX", "S&P 500", "SPY")
    assert index.symbol == "SPY"
    assert await mock.get_news(["AAPL"]) == []
    voo = await mock.get_reference_data("VOO")
    assert voo.expense_ratio == 0.0003
    unknown = await mock.get_reference_data("ZZZZ")
    assert unknown.asset_class is AssetClass.OTHER


def test_seed_sample_portfolios() -> None:
    samples = SeedData(resolve_path("data/seed")).sample_portfolios
    assert len(samples) == 3
    assert all(s["holdings"] for s in samples)


async def test_symbol_table_covers_prices_and_reference_data() -> None:
    mock = make_mock()
    table = {s.symbol: s for s in await mock.list_symbols()}
    assert table["AAPL"].name == "Apple Inc."
    assert "XLRE" in table and table["XLRE"].name == ""  # priced but no reference entry
    assert list(table) == sorted(table)
