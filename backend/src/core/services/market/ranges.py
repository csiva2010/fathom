"""Chart ranges (1D-5Y) mapped to bar timeframes and lookback windows (MD-02)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from src.core.domain.market import Bar, PriceRange


@dataclass(frozen=True)
class RangeSpec:
    timeframe: str
    lookback: timedelta
    intraday: bool
    keep_sessions: int | None = None  # intraday ranges keep only the last N trading days


RANGE_SPECS: dict[PriceRange, RangeSpec] = {
    # Intraday ranges look back further than needed to cover weekends and holidays,
    # then trim to the last N sessions.
    PriceRange.D1: RangeSpec("5Min", timedelta(days=5), intraday=True, keep_sessions=1),
    PriceRange.D5: RangeSpec("30Min", timedelta(days=10), intraday=True, keep_sessions=5),
    PriceRange.M1: RangeSpec("1Day", timedelta(days=31), intraday=False),
    PriceRange.M3: RangeSpec("1Day", timedelta(days=92), intraday=False),
    PriceRange.M6: RangeSpec("1Day", timedelta(days=183), intraday=False),
    PriceRange.Y1: RangeSpec("1Day", timedelta(days=366), intraday=False),
    PriceRange.Y5: RangeSpec("1Week", timedelta(days=5 * 366), intraday=False),
}


def trim_to_sessions(bars: list[Bar], sessions: int | None) -> list[Bar]:
    if not sessions or not bars:
        return bars
    days = sorted({bar.t.date() for bar in bars})
    keep = set(days[-sessions:])
    return [bar for bar in bars if bar.t.date() in keep]
