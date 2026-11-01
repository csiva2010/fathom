"""Sliding-window limiter for quotas counted per fixed window (e.g. "100 per minute").

A token bucket allows a burst on top of its refill rate, which can exceed a hard
per-minute quota. This limiter never lets more than `limit` units through in any
`window_seconds` span, which matches how providers such as the Gemini API count.
"""

from __future__ import annotations

from collections import deque

from src.data.resilience import clock as default_clock


class SlidingWindowLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        *,
        clock: default_clock.Clock = default_clock.monotonic,
        sleep: default_clock.Sleeper = default_clock.sleep,
    ):
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._sleep = sleep
        self._sent: deque[tuple[float, int]] = deque()

    def _used(self, now: float) -> int:
        while self._sent and now - self._sent[0][0] >= self.window:
            self._sent.popleft()
        return sum(count for _, count in self._sent)

    async def acquire(self, units: int = 1) -> None:
        """Wait until `units` more fit in the window, then record them."""
        if units > self.limit:
            raise ValueError(f"cannot acquire {units} units with a limit of {self.limit}")
        while True:
            now = self._clock()
            if self._used(now) + units <= self.limit:
                self._sent.append((now, units))
                return
            # Wait until the oldest entry leaves the window, then re-check.
            await self._sleep(max(0.01, self._sent[0][0] + self.window - now))
