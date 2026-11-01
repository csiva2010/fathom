from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from src.core.domain.market import DataStatus, Freshness
from src.core.domain.portfolio import HoldingInput
from src.core.domain.risk import RiskProfile
from src.core.errors import ProviderUnavailable, ValidationFailed
from src.core.services.market.factory import build_market_service
from src.core.services.market.market_data_service import MarketDataService
from src.core.services.portfolio_service import PortfolioAnalysisService, summarize_freshness
from tests.conftest import make_settings


@pytest.fixture
async def market(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Market service with no provider keys: every number comes from the mock provider."""
    async with httpx.AsyncClient() as client:
        yield build_market_service(make_settings(tmp_path), client)


async def test_analyze_sample_style_portfolio(market: MarketDataService) -> None:
    service = PortfolioAnalysisService(market)
    result = await service.analyze(
        [
            HoldingInput(symbol="aapl", quantity=10, cost_basis=150),
            HoldingInput(symbol="VTI", quantity=20, cost_basis=200),
            HoldingInput(symbol="BND", quantity=30),
            HoldingInput(symbol="ZZZZ", quantity=5),
        ],
        risk_profile=RiskProfile.MODERATE,
    )
    assert {h.symbol for h in result.holdings} == {"AAPL", "VTI", "BND"}
    assert result.unpriced == ["ZZZZ"]
    assert result.total_value > 0
    assert result.weighted_expense_ratio is not None
    assert result.risk.history_days > 200
    assert result.risk.profile is RiskProfile.MODERATE
    assert result.benchmark is not None and result.benchmark.benchmark_symbol == "SPY"
    assert {f.status for f in result.freshness} == {DataStatus.MOCK}
    assert len(result.freshness) == 1  # one stamp per source and status


async def test_analyze_empty_and_invalid(market: MarketDataService) -> None:
    service = PortfolioAnalysisService(market)
    empty = await service.analyze([HoldingInput(symbol="AAPL", quantity=0)])
    assert empty.total_value == 0 and empty.freshness == []
    with pytest.raises(ValidationFailed):
        await service.analyze([HoldingInput(symbol="$$$", quantity=1)])


async def test_analyze_degrades_when_history_and_reference_fail(
    market: MarketDataService, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*args: object, **kwargs: object) -> None:
        raise ProviderUnavailable("alpaca", "down")

    monkeypatch.setattr(market, "get_history", fail)
    monkeypatch.setattr(market, "get_reference_data", fail)
    result = await PortfolioAnalysisService(market).analyze(
        [HoldingInput(symbol="AAPL", quantity=1)]
    )
    assert result.total_value > 0
    assert result.risk.history_days == 0
    assert result.benchmark is None
    assert result.holdings[0].asset_class.value == "other"  # no reference data


async def test_analyze_batches_large_portfolios(
    market: MarketDataService, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    original = market.get_quotes

    async def counting(symbols: list[str]):  # type: ignore[no-untyped-def]
        calls.append(len(symbols))
        return await original(symbols)

    monkeypatch.setattr(market, "get_quotes", counting)
    holdings = [HoldingInput(symbol=f"Z{i:02d}", quantity=1) for i in range(55)]
    result = await PortfolioAnalysisService(market).analyze(holdings)
    assert calls == [50, 5]
    assert len(result.unpriced) == 55


def test_summarize_freshness_keeps_oldest_per_source() -> None:
    old = datetime(2026, 10, 30, tzinfo=UTC)
    new = datetime(2026, 10, 31, tzinfo=UTC)
    stamps = [
        Freshness(source="alpaca", as_of=new, status=DataStatus.LIVE),
        Freshness(source="alpaca", as_of=old, status=DataStatus.LIVE),
        Freshness(source="mock", as_of=new, status=DataStatus.MOCK),
    ]
    summary = summarize_freshness(stamps)
    assert [(f.source, f.as_of) for f in summary] == [("alpaca", old), ("mock", new)]
