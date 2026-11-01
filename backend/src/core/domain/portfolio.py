"""Portfolio analysis domain models (PF-02 to PF-06).

Conventions: weights and expense ratios are fractions (0.25 = 25%); fields ending in
`_percent` are percentages (1.5 = 1.5%).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

from src.core.domain.market import AssetClass, Freshness
from src.core.domain.risk import RiskProfile


class HoldingInput(BaseModel):
    """A user-entered position. Holdings are user data only; nothing is ever traded (AS-07)."""

    symbol: str
    quantity: float = Field(ge=0)
    cost_basis: float | None = Field(default=None, ge=0)  # per share
    asset_class: AssetClass | None = None


class HoldingMetrics(BaseModel):
    symbol: str
    name: str = ""
    asset_class: AssetClass
    quantity: float
    price: float
    market_value: float
    cost_value: float | None = None
    gain: float | None = None
    gain_percent: float | None = None
    weight: float
    sector: str | None = None  # single-company holdings only; funds are looked through
    beta: float | None = None
    expense_ratio: float | None = None


class AllocationSlice(BaseModel):
    label: str
    value: float
    weight: float


class Diversification(BaseModel):
    """Concentration-based score from 0 (one position) to 100 (broadly spread) (PF-03)."""

    score: int
    effective_holdings: float
    effective_sectors: float
    largest_holding: str | None = None
    largest_holding_weight: float = 0.0
    largest_sector: str | None = None
    largest_sector_weight: float = 0.0
    drivers: list[str] = Field(default_factory=list)


class ProfileFit(StrEnum):
    WITHIN = "within"
    ABOVE = "above"  # the portfolio swings more than the profile usually implies
    BELOW = "below"


class RiskMetrics(BaseModel):
    """PF-04. Volatility and drawdown come from today's holdings replayed over history."""

    weighted_beta: float | None = None
    beta_coverage: float = 0.0  # share of portfolio value with a known beta
    annualized_volatility_percent: float | None = None
    max_drawdown_percent: float | None = None
    history_days: int = 0
    risk_level: RiskProfile | None = None
    profile: RiskProfile | None = None
    profile_fit: ProfileFit | None = None


class BenchmarkComparison(BaseModel):
    """PF-05: today's holdings versus the benchmark over the same dates."""

    benchmark_symbol: str
    range: str
    start: date
    end: date
    portfolio_return_percent: float
    benchmark_return_percent: float
    difference_percent: float


class PerformancePoint(BaseModel):
    """Portfolio and benchmark on one date, both rebased to 100 at the start (PF-05)."""

    date: date
    portfolio: float
    benchmark: float


class Observation(BaseModel):
    """An educational learning point about the portfolio, never an instruction (PF-06)."""

    code: str
    message: str


class PortfolioAnalysis(BaseModel):
    total_value: float
    total_cost: float | None = None  # holdings that have a cost basis
    total_gain: float | None = None
    total_gain_percent: float | None = None
    holdings: list[HoldingMetrics]
    allocation_by_holding: list[AllocationSlice]
    allocation_by_asset_class: list[AllocationSlice]
    allocation_by_sector: list[AllocationSlice]
    weighted_expense_ratio: float | None = None
    diversification: Diversification
    risk: RiskMetrics
    benchmark: BenchmarkComparison | None = None
    performance: list[PerformancePoint] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    unpriced: list[str] = Field(default_factory=list)  # symbols we could not price
    freshness: list[Freshness] = Field(default_factory=list)
