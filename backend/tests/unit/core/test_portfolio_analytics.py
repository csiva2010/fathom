from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.core.domain.market import AssetClass, Bar, ReferenceData, SectorWeight
from src.core.domain.portfolio import (
    AllocationSlice,
    HoldingInput,
    HoldingMetrics,
    ProfileFit,
    RiskMetrics,
)
from src.core.domain.risk import RiskProfile
from src.core.services import portfolio_analytics as pa

START = datetime(2026, 1, 5, tzinfo=UTC)

REFERENCE = {
    "AAPL": ReferenceData(
        symbol="AAPL",
        name="Apple",
        asset_class=AssetClass.STOCK,
        sector="Information Technology",
        beta=1.2,
    ),
    "VTI": ReferenceData(
        symbol="VTI",
        name="Total Market",
        asset_class=AssetClass.ETF,
        beta=1.0,
        expense_ratio=0.0003,
        sector_weights=[
            SectorWeight(sector="Information Technology", weight=0.3),
            SectorWeight(sector="Financials", weight=0.2),
        ],
    ),
    "BND": ReferenceData(
        symbol="BND", asset_class=AssetClass.BOND_ETF, beta=0.1, expense_ratio=0.0003
    ),
    "ARKK": ReferenceData(symbol="ARKK", asset_class=AssetClass.ETF, expense_ratio=0.0075),
}


def bars(closes: list[float]) -> list[Bar]:
    return [
        Bar(t=START + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1)
        for i, c in enumerate(closes)
    ]


def metric(
    symbol: str, weight: float, asset_class: AssetClass = AssetClass.STOCK, **kw
) -> HoldingMetrics:  # type: ignore[no-untyped-def]
    return HoldingMetrics(
        symbol=symbol,
        asset_class=asset_class,
        quantity=1,
        price=weight * 100,
        market_value=weight * 100,
        weight=weight,
        **kw,
    )


# --- Holdings and value ------------------------------------------------------


def test_merge_holdings_combines_lots_and_drops_zero_quantity() -> None:
    merged = pa.merge_holdings(
        [
            HoldingInput(symbol="AAPL", quantity=10, cost_basis=100),
            HoldingInput(symbol="AAPL", quantity=10, cost_basis=200, asset_class=AssetClass.STOCK),
            HoldingInput(symbol="VTI", quantity=1, cost_basis=50),
            HoldingInput(symbol="VTI", quantity=1),
            HoldingInput(symbol="ZERO", quantity=0),
        ]
    )
    by_symbol = {h.symbol: h for h in merged}
    assert set(by_symbol) == {"AAPL", "VTI"}
    assert by_symbol["AAPL"].quantity == 20
    assert by_symbol["AAPL"].cost_basis == 150
    assert by_symbol["AAPL"].asset_class is AssetClass.STOCK
    assert by_symbol["VTI"].cost_basis is None  # one lot has no cost basis


def test_value_holdings_computes_gain_and_weights() -> None:
    holdings = [
        HoldingInput(symbol="AAPL", quantity=10, cost_basis=100),
        HoldingInput(symbol="VTI", quantity=30),
        HoldingInput(symbol="MISSING", quantity=5),
    ]
    metrics = pa.value_holdings(holdings, {"AAPL": 150, "VTI": 100}, REFERENCE)
    assert [m.symbol for m in metrics] == ["VTI", "AAPL"]  # largest first
    vti, aapl = metrics
    assert aapl.market_value == 1500 and aapl.cost_value == 1000
    assert aapl.gain == 500 and aapl.gain_percent == 50
    assert aapl.weight == pytest.approx(1500 / 4500)
    assert aapl.sector == "Information Technology" and aapl.expense_ratio is None
    assert vti.gain is None and vti.sector is None and vti.expense_ratio == 0.0003
    # Unknown reference data falls back to the user's asset class or "other".
    [other] = pa.value_holdings([HoldingInput(symbol="X", quantity=1)], {"X": 1}, {})
    assert other.asset_class is AssetClass.OTHER


def test_allocations() -> None:
    metrics = pa.value_holdings(
        [
            HoldingInput(symbol="AAPL", quantity=1),
            HoldingInput(symbol="VTI", quantity=1),
            HoldingInput(symbol="BND", quantity=1),
            HoldingInput(symbol="CASHX", quantity=1, asset_class=AssetClass.CASH),
            HoldingInput(symbol="ODD", quantity=1),
        ],
        {"AAPL": 100, "VTI": 100, "BND": 100, "CASHX": 100, "ODD": 100},
        {**REFERENCE, "BND": ReferenceData(symbol="BND", asset_class=AssetClass.BOND_ETF)},
    )
    by_class = {s.label: s.weight for s in pa.allocation_by_asset_class(metrics)}
    assert by_class == {"stock": 0.2, "etf": 0.2, "bond_etf": 0.2, "cash": 0.2, "other": 0.2}

    sectors = {s.label: s.value for s in pa.allocation_by_sector(metrics, REFERENCE)}
    # VTI is looked through: 30% tech, 20% financials, the uncovered 50% is "Other".
    assert sectors["Information Technology"] == 130
    assert sectors["Financials"] == 20
    assert sectors["Other"] == 50
    assert sectors["Fixed Income"] == 100
    assert sectors["Cash"] == 100
    assert sectors[pa.UNCLASSIFIED] == 100
    labels = {s.label for s in pa.allocation_by_holding(metrics)}
    assert labels == {"AAPL", "VTI", "BND", "CASHX", "ODD"}


def test_weighted_expense_ratio() -> None:
    stock = metric("AAPL", 0.5)
    fund = metric("VTI", 0.5, AssetClass.ETF, expense_ratio=0.001)
    assert pa.weighted_expense_ratio([stock, fund]) == pytest.approx(0.0005)
    assert pa.weighted_expense_ratio([]) is None
    unknown_fee = metric("NEWF", 0.5, AssetClass.ETF)
    assert pa.weighted_expense_ratio([stock, unknown_fee]) is None


# --- Diversification ---------------------------------------------------------


def test_diversification_single_stock_scores_zero() -> None:
    only = metric("AAPL", 1.0)
    result = pa.diversification([only], [AllocationSlice(label="Tech", value=100, weight=1)])
    assert result.score == 0
    assert result.largest_holding == "AAPL"
    assert result.effective_holdings == 1
    assert any("AAPL" in d for d in result.drivers)


def test_diversification_funds_count_as_broad_baskets() -> None:
    funds = [metric("VTI", 0.5, AssetClass.ETF), metric("BND", 0.5, AssetClass.BOND_ETF)]
    stocks = [metric("AAPL", 0.5), metric("MSFT", 0.5)]
    sectors = [AllocationSlice(label=f"S{i}", value=1, weight=0.125) for i in range(8)]
    assert pa.diversification(funds, sectors).score == 100
    assert pa.diversification(stocks, sectors).score < 60
    assert pa.diversification([], []).score == 0
    assert pa.diversification(stocks, []).largest_sector is None


# --- Risk and benchmark ------------------------------------------------------


def test_weighted_beta_renormalises_over_known_betas() -> None:
    beta, coverage = pa.weighted_beta(
        [metric("A", 0.5, beta=1.5), metric("B", 0.25, beta=0.5), metric("C", 0.25)]
    )
    assert coverage == 0.75
    assert beta == pytest.approx((0.5 * 1.5 + 0.25 * 0.5) / 0.75)
    assert pa.weighted_beta([metric("C", 1.0)]) == (None, 0.0)


def test_value_series_uses_common_dates() -> None:
    series = pa.value_series(
        {"A": 2, "B": 1, "C": 1},
        {"A": bars([10, 11, 12]), "B": bars([5, 5]), "C": [], "D": bars([1])},
    )
    assert series == [(START.date(), 25), ((START + timedelta(days=1)).date(), 27)]
    assert pa.value_series({"A": 1}, {}) == []


@pytest.mark.parametrize(
    ("volatility", "expected"),
    [
        (5, RiskProfile.CONSERVATIVE),
        (10, RiskProfile.CONSERVATIVE),
        (12, RiskProfile.MODERATE),
        (25, RiskProfile.AGGRESSIVE),
    ],
)
def test_classify_volatility(volatility: float, expected: RiskProfile) -> None:
    assert pa.classify_volatility(volatility) is expected


def test_profile_fit() -> None:
    assert pa.profile_fit(RiskProfile.AGGRESSIVE, RiskProfile.MODERATE) is ProfileFit.ABOVE
    assert pa.profile_fit(RiskProfile.CONSERVATIVE, RiskProfile.MODERATE) is ProfileFit.BELOW
    assert pa.profile_fit(RiskProfile.MODERATE, RiskProfile.MODERATE) is ProfileFit.WITHIN


def test_risk_metrics_with_and_without_history() -> None:
    swings = [(date(2026, 1, d), v) for d, v in enumerate([100, 110, 95, 120, 90], start=1)]
    risk = pa.risk_metrics([metric("A", 1.0, beta=1.3)], swings, RiskProfile.CONSERVATIVE)
    assert risk.weighted_beta == 1.3
    assert risk.history_days == 5
    assert risk.max_drawdown_percent == -25
    assert risk.risk_level is RiskProfile.AGGRESSIVE
    assert risk.profile_fit is ProfileFit.ABOVE

    empty = pa.risk_metrics([], [], RiskProfile.MODERATE)
    assert empty.annualized_volatility_percent is None
    assert empty.max_drawdown_percent is None
    assert empty.profile_fit is None


def test_compare_to_benchmark() -> None:
    series = [(START.date() + timedelta(days=i), v) for i, v in enumerate([100, 105, 110])]
    result = pa.compare_to_benchmark(series, bars([50, 52, 55, 60]), "SPY", "1Y")
    assert result is not None
    assert result.portfolio_return_percent == 10
    assert result.benchmark_return_percent == 10
    assert result.difference_percent == 0
    assert result.start == START.date()
    assert pa.compare_to_benchmark(series[:1], bars([50]), "SPY", "1Y") is None
    zero = [(START.date(), 0.0), (START.date() + timedelta(days=1), 5.0)]
    assert pa.compare_to_benchmark(zero, bars([50, 55]), "SPY", "1Y") is None


# --- Observations ------------------------------------------------------------


def test_observations_cover_each_learning_point() -> None:
    metrics = [
        metric("NVDA", 0.6, sector="Information Technology"),
        metric("ARKK", 0.4, AssetClass.ETF, expense_ratio=0.0075),
    ]
    sectors = [
        AllocationSlice(label="Information Technology", value=60, weight=0.6),
        AllocationSlice(label="Other", value=40, weight=0.4),
    ]
    div = pa.diversification(metrics, sectors)
    risk = RiskMetrics(
        risk_level=RiskProfile.AGGRESSIVE,
        profile=RiskProfile.CONSERVATIVE,
        profile_fit=ProfileFit.ABOVE,
    )
    notes = pa.observations(metrics, sectors, div, risk, unpriced=["ZZZZ"])
    codes = [n.code for n in notes]
    assert codes == [
        "single_position",
        "sector_concentration",
        "high_fee_fund",
        "all_equity",
        "low_diversification",
        "risk_above_profile",
        "unpriced_symbols",
    ]
    assert "it is left out" in notes[-1].message
    # Educational framing only: no instructions to trade.
    for note in notes:
        lowered = note.message.lower()
        assert not any(word in lowered for word in ("you should", " buy ", " sell "))


def test_observations_for_a_calm_balanced_portfolio() -> None:
    metrics = [metric("VTI", 0.5, AssetClass.ETF), metric("BND", 0.5, AssetClass.BOND_ETF)]
    risk = RiskMetrics(
        risk_level=RiskProfile.CONSERVATIVE,
        profile=RiskProfile.AGGRESSIVE,
        profile_fit=ProfileFit.BELOW,
    )
    notes = pa.observations(metrics, [], pa.diversification(metrics, []), risk, ["A", "B"])
    assert [n.code for n in notes] == ["risk_below_profile", "unpriced_symbols"]
    assert "they are left out" in notes[-1].message


# --- Full analysis -----------------------------------------------------------


def test_analyze_end_to_end() -> None:
    result = pa.analyze(
        [
            HoldingInput(symbol="AAPL", quantity=10, cost_basis=100),
            HoldingInput(symbol="VTI", quantity=10, cost_basis=90),
            HoldingInput(symbol="BND", quantity=10),
            HoldingInput(symbol="GONE", quantity=3),
        ],
        {"AAPL": 120, "VTI": 100, "BND": 80},
        REFERENCE,
        {"AAPL": bars([100, 110, 120]), "VTI": bars([95, 98, 100]), "BND": bars([80, 80, 80])},
        risk_profile=RiskProfile.MODERATE,
        benchmark_bars=bars([400, 404, 410]),
    )
    assert result.total_value == 3000
    assert result.total_cost == 1900  # BND has no cost basis
    assert result.total_gain == 300
    assert result.total_gain_percent == pytest.approx(15.79, abs=0.01)
    assert result.unpriced == ["GONE"]
    assert result.weighted_expense_ratio == pytest.approx((1000 * 0.0003 + 800 * 0.0003) / 3000)
    assert result.benchmark is not None and result.benchmark.benchmark_symbol == "SPY"
    assert result.risk.history_days == 3
    assert result.risk.profile is RiskProfile.MODERATE
    assert "unpriced_symbols" in {o.code for o in result.observations}


def test_analyze_empty_portfolio() -> None:
    result = pa.analyze([], {}, {}, {})
    assert result.total_value == 0
    assert result.total_cost is None and result.total_gain_percent is None
    assert result.holdings == [] and result.observations == []
    assert result.diversification.score == 0
    assert result.benchmark is None
