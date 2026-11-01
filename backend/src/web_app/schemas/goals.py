from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from src.core.domain.goals import ExampleAllocation, GoalProjection
from src.core.domain.risk import RiskProfile


class GoalType(StrEnum):
    RETIREMENT = "retirement"
    HOUSE = "house"
    EMERGENCY = "emergency"
    EDUCATION = "education"
    OTHER = "other"


class GoalIn(BaseModel):
    """GL-02. Without a risk profile the goal uses the user's own (moderate if unset)."""

    type: GoalType
    name: str = Field(default="", max_length=120)
    target_amount: float = Field(gt=0, le=100_000_000)
    target_date: date
    current_savings: float = Field(default=0, ge=0, le=100_000_000)
    monthly_contribution: float = Field(default=0, ge=0, le=1_000_000)
    risk_profile: RiskProfile | None = None


class GoalOut(BaseModel):
    id: str
    type: GoalType
    name: str
    target_amount: float
    target_date: date
    current_savings: float
    monthly_contribution: float
    risk_profile: RiskProfile
    created_at: datetime
    # Null when the goal can't be projected any more (e.g. its date has passed).
    projection: GoalProjection | None
    projection_error: str | None = None


class GoalList(BaseModel):
    goals: list[GoalOut]


class ProjectionOut(BaseModel):
    """Projection for given inputs (GL-03), plus the textbook mix for the profile (GL-04)."""

    projection: GoalProjection
    example_allocation: ExampleAllocation
