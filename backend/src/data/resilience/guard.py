"""ProviderGuard: rate limit + retry + circuit breaker around every provider call."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from src.core.config.settings import MarketConfig
from src.core.errors import CircuitOpen, ProviderError
from src.core.logging import get_logger
from src.data.resilience.circuit_breaker import BreakerState, CircuitBreaker
from src.data.resilience.rate_limiter import TokenBucket
from src.data.resilience.retry import RetryPolicy, with_retry

T = TypeVar("T")
log = get_logger(__name__)


class ProviderGuard:
    def __init__(
        self,
        name: str,
        limiter: TokenBucket,
        breaker: CircuitBreaker,
        retry_policy: RetryPolicy,
    ):
        self.name = name
        self.limiter = limiter
        self.breaker = breaker
        self.retry_policy = retry_policy

    @classmethod
    def from_config(
        cls, name: str, requests_per_minute: int, market: MarketConfig
    ) -> ProviderGuard:
        return cls(
            name=name,
            limiter=TokenBucket.per_minute(requests_per_minute),
            breaker=CircuitBreaker(
                market.circuit_breaker.failure_threshold, market.circuit_breaker.reset_seconds
            ),
            retry_policy=RetryPolicy(
                market.retry.attempts,
                market.retry.base_delay_seconds,
                market.retry.max_delay_seconds,
            ),
        )

    @property
    def state(self) -> BreakerState:
        return self.breaker.state

    async def call(self, operation: str, fn: Callable[[], Awaitable[T]]) -> T:
        if not self.breaker.allow_request():
            raise CircuitOpen(self.name, "temporarily skipped after repeated failures")

        async def attempt() -> T:
            await self.limiter.acquire()
            return await fn()

        try:
            result = await with_retry(attempt, self.retry_policy)
        except ProviderError as error:
            # Bad responses (e.g. an unknown symbol) are not provider outages.
            if error.retryable:
                self.breaker.record_failure()
            log.warning(
                "provider call failed",
                extra={"provider": self.name, "operation": operation, "error": error.code},
            )
            raise
        self.breaker.record_success()
        return result
