"""Market indicators as pure functions over prices and bars (MD-08).

No I/O here: callers fetch bars through MarketDataService and pass them in, so every
number is unit-tested without a network. Percent results are percentages (1.5 = 1.5%).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Sequence
from datetime import timedelta
from itertools import pairwise
from typing import TypeVar

from src.core.domain.market import Bar, Indicators

T = TypeVar("T")

TRADING_DAYS_PER_YEAR = 252
VOLATILITY_WINDOW = 30


def percent_change(start: float, end: float) -> float | None:
    if start == 0:
        return None
    return (end - start) / start * 100


def simple_moving_average(values: Sequence[float], window: int) -> float | None:
    """Mean of the last `window` values, or None when there is not enough history."""
    if window <= 0 or len(values) < window:
        return None
    return sum(values[-window:]) / window


def period_returns(values: Sequence[float]) -> list[float]:
    """Simple returns between consecutive values; steps from a zero value are skipped."""
    return [b / a - 1 for a, b in pairwise(values) if a != 0]


def annualized_volatility(
    values: Sequence[float],
    window: int | None = VOLATILITY_WINDOW,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float | None:
    """Sample standard deviation of returns over the last `window` periods, annualized.

    `window=None` uses the whole series. Needs at least two returns.
    """
    series = values if window is None else values[-(window + 1) :]
    returns = period_returns(series)
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(periods_per_year) * 100


def max_drawdown(values: Sequence[float]) -> float | None:
    """Largest peak-to-trough fall, as a negative percentage (0.0 if it never fell)."""
    if not values:
        return None
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak * 100)
    return worst


def range_position(low: float, high: float, price: float) -> float | None:
    """Where `price` sits between `low` (0) and `high` (100)."""
    if high <= low:
        return None
    return min(100.0, max(0.0, (price - low) / (high - low) * 100))


def week52_range(bars: Sequence[Bar]) -> tuple[float, float] | None:
    """Lowest low and highest high over the 52 weeks ending at the last bar."""
    if not bars:
        return None
    cutoff = bars[-1].t - timedelta(weeks=52)
    window = [bar for bar in bars if bar.t >= cutoff]
    return min(bar.low for bar in window), max(bar.high for bar in window)


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def compute_indicators(symbol: str, bars: Sequence[Bar]) -> Indicators:
    """All MD-08 indicators for one symbol from daily bars, oldest first."""
    if not bars:
        raise ValueError("compute_indicators needs at least one bar")
    closes = [bar.close for bar in bars]
    last = closes[-1]
    sma_50 = simple_moving_average(closes, 50)
    sma_200 = simple_moving_average(closes, 200)
    low_high = week52_range(bars)
    low, high = low_high if low_high else (None, None)
    return Indicators(
        symbol=symbol,
        last_close=last,
        as_of=bars[-1].t,
        period_change_percent=_round(percent_change(closes[0], last)),
        sma_50=_round(sma_50),
        sma_200=_round(sma_200),
        price_vs_sma_50_percent=_round(percent_change(sma_50, last) if sma_50 else None),
        price_vs_sma_200_percent=_round(percent_change(sma_200, last) if sma_200 else None),
        week52_low=low,
        week52_high=high,
        week52_position_percent=_round(
            range_position(low, high, last) if low is not None and high is not None else None,
            1,
        ),
        volatility_30d_percent=_round(annualized_volatility(closes)),
        max_drawdown_percent=_round(max_drawdown(closes)),
        bars_used=len(bars),
    )


def rank_movers(
    items: Sequence[T], change: Callable[[T], float | None], limit: int = 5
) -> tuple[list[T], list[T]]:
    """Top gainers (biggest rise first) and losers (biggest fall first).

    Items without a change are ignored; flat items are neither gainers nor losers.
    """
    known = [(item, value) for item in items if (value := change(item)) is not None]
    gainers = sorted((p for p in known if p[1] > 0), key=lambda p: p[1], reverse=True)
    losers = sorted((p for p in known if p[1] < 0), key=lambda p: p[1])
    return [item for item, _ in gainers[:limit]], [item for item, _ in losers[:limit]]
