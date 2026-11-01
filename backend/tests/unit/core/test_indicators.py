from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from src.core.domain.market import Bar
from src.core.services.indicators import (
    annualized_volatility,
    compute_indicators,
    max_drawdown,
    percent_change,
    period_returns,
    range_position,
    rank_movers,
    simple_moving_average,
    week52_range,
)

START = datetime(2025, 1, 1, tzinfo=UTC)


def bars_from(closes: list[float], step: timedelta = timedelta(days=1)) -> list[Bar]:
    return [
        Bar(t=START + step * i, open=c, high=c + 1, low=c - 1, close=c, volume=100)
        for i, c in enumerate(closes)
    ]


def test_percent_change_and_zero_start() -> None:
    assert percent_change(100, 110) == pytest.approx(10)
    assert percent_change(0, 5) is None


def test_simple_moving_average_needs_full_window() -> None:
    assert simple_moving_average([1, 2, 3, 4], 2) == 3.5
    assert simple_moving_average([1, 2], 3) is None
    assert simple_moving_average([1, 2], 0) is None


def test_period_returns_skip_zero_values() -> None:
    assert period_returns([100, 110, 0, 5]) == pytest.approx([0.1, -1.0])


def test_annualized_volatility() -> None:
    closes = [100, 101, 100, 101, 100]
    returns = period_returns(closes)
    mean = sum(returns) / len(returns)
    stdev = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
    assert annualized_volatility(closes, window=None) == pytest.approx(stdev * math.sqrt(252) * 100)
    # A window uses only the most recent returns.
    assert annualized_volatility([50, 200, *closes], window=4) == pytest.approx(
        annualized_volatility(closes, window=None)
    )
    assert annualized_volatility([100, 101]) is None
    assert annualized_volatility([100, 100, 100], window=None) == 0


def test_max_drawdown() -> None:
    assert max_drawdown([100, 120, 90, 130, 117]) == pytest.approx(-25)
    assert max_drawdown([1, 2, 3]) == 0
    assert max_drawdown([]) is None
    assert max_drawdown([0, 0]) == 0


def test_range_position() -> None:
    assert range_position(10, 20, 15) == 50
    assert range_position(10, 20, 25) == 100
    assert range_position(10, 20, 5) == 0
    assert range_position(10, 10, 10) is None


def test_week52_range_uses_last_52_weeks() -> None:
    bars = bars_from([500.0] + [100.0] * 400)  # the first bar is more than a year old
    assert week52_range(bars) == (99.0, 101.0)
    assert week52_range([]) is None


def test_compute_indicators_full_history() -> None:
    closes = [100 + i * 0.5 for i in range(250)]
    result = compute_indicators("AAPL", bars_from(closes))
    assert result.symbol == "AAPL"
    assert result.last_close == closes[-1]
    assert result.sma_50 == pytest.approx(sum(closes[-50:]) / 50, abs=0.01)
    assert result.sma_200 == pytest.approx(sum(closes[-200:]) / 200, abs=0.01)
    assert result.price_vs_sma_50_percent is not None and result.price_vs_sma_50_percent > 0
    assert result.week52_low == closes[0] - 1
    assert result.week52_high == closes[-1] + 1
    assert result.max_drawdown_percent == 0
    assert result.volatility_30d_percent is not None
    assert result.bars_used == 250


def test_compute_indicators_short_history_and_empty() -> None:
    result = compute_indicators("NEW", bars_from([10.0]))
    assert result.sma_50 is None and result.sma_200 is None
    assert result.price_vs_sma_50_percent is None
    assert result.volatility_30d_percent is None
    assert result.period_change_percent == 0
    with pytest.raises(ValueError):
        compute_indicators("X", [])


def test_rank_movers() -> None:
    changes = {"A": 3.0, "B": -2.0, "C": None, "D": 5.0, "E": -4.0, "F": 0.0}
    gainers, losers = rank_movers(list(changes), changes.get, limit=5)
    assert gainers == ["D", "A"]
    assert losers == ["E", "B"]
    top, bottom = rank_movers(list(changes), changes.get, limit=1)
    assert (top, bottom) == (["D"], ["E"])
