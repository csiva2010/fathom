"""Goal projections as pure functions (GL-03, GL-04).

Money compounds monthly and contributions are made at the end of each month. Return
scenarios are fixed educational assumptions per risk profile, not forecasts.
"""

from __future__ import annotations

from datetime import date

from src.core.domain.goals import (
    ExampleAllocation,
    ExampleAllocationSlice,
    GoalProjection,
    ProjectionPoint,
    ProjectionRequest,
    Scenario,
    ScenarioResult,
)
from src.core.domain.risk import RiskProfile
from src.core.errors import ValidationFailed

MAX_MONTHS = 70 * 12

# Nominal yearly returns (percent) per scenario. The spread widens with risk.
RETURN_ASSUMPTIONS: dict[RiskProfile, dict[Scenario, float]] = {
    RiskProfile.CONSERVATIVE: {
        Scenario.PESSIMISTIC: 2.0,
        Scenario.EXPECTED: 4.0,
        Scenario.OPTIMISTIC: 5.5,
    },
    RiskProfile.MODERATE: {
        Scenario.PESSIMISTIC: 1.5,
        Scenario.EXPECTED: 5.5,
        Scenario.OPTIMISTIC: 8.0,
    },
    RiskProfile.AGGRESSIVE: {
        Scenario.PESSIMISTIC: 1.0,
        Scenario.EXPECTED: 7.0,
        Scenario.OPTIMISTIC: 10.0,
    },
}

# Generic textbook mixes (stocks / bonds / cash), shown as education only (GL-04).
EXAMPLE_ALLOCATIONS: dict[RiskProfile, dict[str, float]] = {
    RiskProfile.CONSERVATIVE: {"stocks": 0.30, "bonds": 0.60, "cash": 0.10},
    RiskProfile.MODERATE: {"stocks": 0.60, "bonds": 0.35, "cash": 0.05},
    RiskProfile.AGGRESSIVE: {"stocks": 0.85, "bonds": 0.15, "cash": 0.0},
}

EXAMPLE_ALLOCATION_NOTE = (
    "A generic textbook example for this risk level, for learning only. It is not a "
    "recommendation for your situation."
)


def months_until(today: date, target: date) -> int:
    """Whole calendar months from today to the target date (at least 1)."""
    if target <= today:
        raise ValidationFailed("The goal's target date must be in the future.")
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if target.day < today.day:
        months -= 1
    months = max(1, months)
    if months > MAX_MONTHS:
        raise ValidationFailed("The goal's target date must be within 70 years.")
    return months


def monthly_rate(annual_return_percent: float) -> float:
    return float((1 + annual_return_percent / 100) ** (1 / 12) - 1)


def future_value(
    present: float, monthly_contribution: float, annual_return_percent: float, months: int
) -> float:
    rate = monthly_rate(annual_return_percent)
    if rate == 0:
        return present + monthly_contribution * months
    growth = (1 + rate) ** months
    return float(present * growth + monthly_contribution * (growth - 1) / rate)


def required_monthly_contribution(
    target: float, present: float, annual_return_percent: float, months: int
) -> float:
    """Monthly amount needed to reach `target`; 0 when savings alone get there."""
    if months <= 0:
        raise ValueError("months must be positive")
    rate = monthly_rate(annual_return_percent)
    if rate == 0:
        needed = (target - present) / months
    else:
        growth = (1 + rate) ** months
        needed = (target - present * growth) * rate / (growth - 1)
    return max(0.0, needed)


def real_value(nominal: float, inflation_percent: float, months: int) -> float:
    """Express a future amount in today's dollars."""
    return float(nominal / (1 + inflation_percent / 100) ** (months / 12))


def _add_months(start: date, months: int) -> date:
    year, month = divmod(start.month - 1 + months, 12)
    year += start.year
    month += 1
    # Clamp the day for shorter months (e.g. Jan 31 + 1 month -> Feb 28).
    for day in (start.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise AssertionError("unreachable")  # pragma: no cover


def project_goal(request: ProjectionRequest, today: date) -> GoalProjection:
    """Three return scenarios, inflation-adjusted values and the monthly amount needed."""
    months = months_until(today, request.target_date)
    returns = RETURN_ASSUMPTIONS[request.risk_profile]
    present, monthly = request.current_savings, request.monthly_contribution

    scenarios: list[ScenarioResult] = []
    for scenario, annual in returns.items():
        final = future_value(present, monthly, annual, months)
        scenarios.append(
            ScenarioResult(
                scenario=scenario,
                annual_return_percent=annual,
                final_value=round(final, 2),
                final_value_real=round(real_value(final, request.inflation_percent, months), 2),
                reaches_target=final >= request.target_amount,
                shortfall=round(max(0.0, request.target_amount - final), 2),
                required_monthly_contribution=round(
                    required_monthly_contribution(request.target_amount, present, annual, months),
                    2,
                ),
            )
        )

    points = sorted({*range(0, months, 12), months})
    series = [
        ProjectionPoint(
            month=m,
            date=_add_months(today, m),
            contributed=round(present + monthly * m, 2),
            values={s: round(future_value(present, monthly, r, m), 2) for s, r in returns.items()},
        )
        for m in points
    ]

    return GoalProjection(
        months=months,
        target_amount=request.target_amount,
        target_amount_real=round(
            real_value(request.target_amount, request.inflation_percent, months), 2
        ),
        inflation_percent=request.inflation_percent,
        total_contributed=round(present + monthly * months, 2),
        scenarios=scenarios,
        series=series,
        assumptions=(
            f"Yearly returns of {', '.join(f'{r:g}%' for r in returns.values())} "
            f"(pessimistic, expected, optimistic) for a {request.risk_profile.value} mix, "
            f"compounded monthly, with {request.inflation_percent:g}% yearly inflation. "
            "These are illustrative assumptions, not predictions."
        ),
    )


def example_allocation(profile: RiskProfile) -> ExampleAllocation:
    return ExampleAllocation(
        risk_profile=profile,
        slices=[
            ExampleAllocationSlice(asset_class=name, weight=weight)
            for name, weight in EXAMPLE_ALLOCATIONS[profile].items()
        ],
        note=EXAMPLE_ALLOCATION_NOTE,
    )
