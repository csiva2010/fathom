"""Async token-bucket rate limiter, one per provider (MD-06)."""

from __future__ import annotations

import asyncio

from src.data.resilience import clock as default_clock


class TokenBucket:
    """Allows `capacity` requests in a burst, refilling at `rate_per_second`.

    `acquire()` waits until a token is available instead of failing, so callers are
    smoothed under the provider's limit.
    """

    def __init__(
        self,
        rate_per_second: float,
        capacity: float | None = None,
        *,
        clock: default_clock.Clock = default_clock.monotonic,
        sleep: default_clock.Sleeper = default_clock.sleep,
    ):
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self.rate = rate_per_second
        self.capacity = capacity if capacity is not None else max(1.0, rate_per_second)
        self._tokens = self.capacity
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = asyncio.Lock()

    @classmethod
    def per_minute(cls, requests_per_minute: int, **kwargs: object) -> TokenBucket:
        rate = requests_per_minute / 60.0
        # Burst up to the per-minute allowance but never less than one request.
        return cls(rate, capacity=max(1.0, float(requests_per_minute)), **kwargs)  # type: ignore[arg-type]

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated)
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._updated = now

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await self._sleep((1 - self._tokens) / self.rate)
