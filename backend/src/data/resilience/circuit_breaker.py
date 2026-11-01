"""Circuit breaker: after N consecutive failures a provider is skipped for a cool-down."""

from __future__ import annotations

from enum import StrEnum

from src.data.resilience import clock as default_clock


class BreakerState(StrEnum):
    CLOSED = "closed"  # healthy, calls go through
    OPEN = "open"  # skipping the provider
    HALF_OPEN = "half_open"  # cool-down over, next call is a trial


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_seconds: float = 60,
        *,
        clock: default_clock.Clock = default_clock.monotonic,
    ):
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> BreakerState:
        if self._opened_at is None:
            return BreakerState.CLOSED
        if self._clock() - self._opened_at >= self.reset_seconds:
            return BreakerState.HALF_OPEN
        return BreakerState.OPEN

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    def allow_request(self) -> bool:
        return self.state is not BreakerState.OPEN

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self.state is BreakerState.HALF_OPEN or self._failures >= self.failure_threshold:
            self._opened_at = self._clock()
