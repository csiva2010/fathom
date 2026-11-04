"""Hard cap on provider calls per period (e.g. per UTC day), so a busy or abused demo
cannot use up a provider account's allowance (MD-06).

Unlike the token bucket this never waits: once the period's budget is spent, calls are
refused until the next period starts and the chain serves cached or mock data instead.
Counts live in memory, so a restart starts a fresh period count.
"""

from __future__ import annotations

from src.data.resilience import clock as default_clock

DAY_SECONDS = 86_400.0


class UsageBudget:
    def __init__(
        self,
        limit: int,
        period_seconds: float = DAY_SECONDS,
        *,
        clock: default_clock.Clock = default_clock.wall,
    ):
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.limit = limit
        self.period = period_seconds
        self._clock = clock
        self._period_index = self._current_period()
        self._used = 0

    def _current_period(self) -> int:
        # With the wall clock, daily periods start at midnight UTC.
        return int(self._clock() // self.period)

    def _roll(self) -> None:
        period = self._current_period()
        if period != self._period_index:
            self._period_index = period
            self._used = 0

    @property
    def used(self) -> int:
        self._roll()
        return self._used

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    @property
    def resets_in(self) -> float:
        """Seconds until the current period ends."""
        return (self._current_period() + 1) * self.period - self._clock()

    def try_consume(self) -> bool:
        self._roll()
        if self._used >= self.limit:
            return False
        self._used += 1
        return True
