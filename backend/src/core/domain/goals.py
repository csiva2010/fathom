"""Goal projection domain models (GL-03, GL-04)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

from src.core.domain.risk import RiskProfile


class Scenario(StrEnum):
    PESSIMISTIC = "pessimistic"
    EXPECTED = "expected"
    OPTIMISTIC = "optimistic"


class ProjectionRequest(BaseModel):
    target_amount: float = Field(gt=0)
    target_date: date
    current_savings: float = Field(default=0, ge=0)
    monthly_contribution: float = Field(default=0, ge=0)
    risk_profile: RiskProfile = RiskProfile.MODERATE
    inflation_percent: float = Field(default=2.5, ge=0, le=15)


class ScenarioResult(BaseModel):
    scenario: Scenario
    annual_return_percent: float
    final_value: float
    final_value_real: float  # in today's dollars
    reaches_target: bool
    shortfall: float  # 0 when the target is reached
    required_monthly_contribution: float  # to reach the target under this scenario


class ProjectionPoint(BaseModel):
    month: int
    date: date
    contributed: float  # current savings plus contributions so far
    values: dict[Scenario, float]


class GoalProjection(BaseModel):
    months: int
    target_amount: float
    target_amount_real: float  # the target expressed in today's dollars
    inflation_percent: float
    total_contributed: float
    scenarios: list[ScenarioResult]
    series: list[ProjectionPoint]  # yearly points plus the final month, for the chart
    assumptions: str


class ExampleAllocationSlice(BaseModel):
    asset_class: str
    weight: float


class ExampleAllocation(BaseModel):
    """A generic textbook mix for a risk profile, shown as education only (GL-04)."""

    risk_profile: RiskProfile
    slices: list[ExampleAllocationSlice]
    note: str
