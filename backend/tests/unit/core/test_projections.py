from __future__ import annotations

from datetime import date

import pytest

from src.core.domain.goals import ProjectionRequest, Scenario
from src.core.domain.risk import RiskProfile
from src.core.errors import ValidationFailed
from src.core.services import projections as pj

TODAY = date(2026, 10, 31)


def test_months_until() -> None:
    assert pj.months_until(TODAY, date(2027, 10, 31)) == 12
    assert pj.months_until(TODAY, date(2027, 10, 30)) == 11
    assert pj.months_until(TODAY, date(2026, 11, 2)) == 1  # at least one month
    with pytest.raises(ValidationFailed):
        pj.months_until(TODAY, TODAY)
    with pytest.raises(ValidationFailed):
        pj.months_until(TODAY, date(2100, 1, 1))


def test_monthly_rate_compounds_to_the_annual_rate() -> None:
    assert (1 + pj.monthly_rate(6)) ** 12 == pytest.approx(1.06)
    assert pj.monthly_rate(0) == 0


def test_future_value() -> None:
    assert pj.future_value(1000, 100, 0, 12) == 2200
    # One year at 6%: savings grow by exactly 6%.
    assert pj.future_value(1000, 0, 6, 12) == pytest.approx(1060)
    rate = pj.monthly_rate(6)
    expected = 1000 * 1.06 + 100 * ((1 + rate) ** 12 - 1) / rate
    assert pj.future_value(1000, 100, 6, 12) == pytest.approx(expected)


def test_required_monthly_contribution_round_trips() -> None:
    needed = pj.required_monthly_contribution(50_000, 5_000, 5, 60)
    assert pj.future_value(5_000, needed, 5, 60) == pytest.approx(50_000)
    assert pj.required_monthly_contribution(1200, 0, 0, 12) == 100
    assert pj.required_monthly_contribution(1000, 5000, 5, 12) == 0  # already there
    with pytest.raises(ValueError):
        pj.required_monthly_contribution(1000, 0, 5, 0)


def test_real_value() -> None:
    assert pj.real_value(1025, 2.5, 12) == pytest.approx(1000)
    assert pj.real_value(1000, 0, 120) == 1000


def test_project_goal() -> None:
    request = ProjectionRequest(
        target_amount=100_000,
        target_date=date(2036, 10, 31),
        current_savings=10_000,
        monthly_contribution=500,
        risk_profile=RiskProfile.MODERATE,
    )
    result = pj.project_goal(request, TODAY)
    assert result.months == 120
    assert result.total_contributed == 70_000
    assert [s.scenario for s in result.scenarios] == list(Scenario)

    finals = [s.final_value for s in result.scenarios]
    assert finals == sorted(finals)  # pessimistic < expected < optimistic
    for scenario in result.scenarios:
        assert scenario.final_value_real < scenario.final_value
        assert scenario.reaches_target == (scenario.final_value >= 100_000)
        assert scenario.shortfall == pytest.approx(max(0.0, 100_000 - scenario.final_value))
    assert result.scenarios[0].required_monthly_contribution > 500

    assert result.target_amount_real < 100_000
    assert [p.month for p in result.series] == list(range(0, 121, 12))
    assert result.series[0].values[Scenario.EXPECTED] == 10_000
    assert result.series[-1].date == date(2036, 10, 31)
    assert "5.5%" in result.assumptions and "moderate" in result.assumptions


def test_project_goal_series_ends_on_a_partial_year() -> None:
    request = ProjectionRequest(target_amount=1000, target_date=date(2028, 3, 31))
    result = pj.project_goal(request, date(2026, 1, 31))
    assert [p.month for p in result.series] == [0, 12, 24, 26]
    assert result.series[-1].date == date(2028, 3, 31)


def test_add_months_clamps_short_months() -> None:
    assert pj._add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert pj._add_months(date(2026, 1, 31), 3) == date(2026, 4, 30)
    assert pj._add_months(date(2027, 12, 31), 2) == date(2028, 2, 29)


def test_example_allocations_sum_to_one_and_are_labelled() -> None:
    for profile in RiskProfile:
        allocation = pj.example_allocation(profile)
        assert sum(s.weight for s in allocation.slices) == pytest.approx(1)
        assert "not a recommendation" in allocation.note
    stocks = {p: pj.example_allocation(p).slices[0].weight for p in RiskProfile}
    assert (
        stocks[RiskProfile.CONSERVATIVE]
        < stocks[RiskProfile.MODERATE]
        < stocks[RiskProfile.AGGRESSIVE]
    )
