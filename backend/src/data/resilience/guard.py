"""ProviderGuard: budget + rate limit + retry + circuit breaker around every provider call."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from src.core.config.settings import MarketConfig
from src.core.errors import CircuitOpen, ProviderError, ProviderQuotaExceeded
from src.core.logging import get_logger
from src.data.resilience.circuit_breaker import BreakerState, CircuitBreaker
from src.data.resilience.rate_limiter import TokenBucket, WaitTooLong
from src.data.resilience.retry import RetryPolicy, with_retry
from src.data.resilience.usage_budget import UsageBudget

T = TypeVar("T")
log = get_logger(__name__)


class ProviderGuard:
    def __init__(
        self,
        name: str,
        limiter: TokenBucket,
        breaker: CircuitBreaker,
        retry_policy: RetryPolicy,
        *,
        budget: UsageBudget | None = None,
        max_wait_seconds: float | None = None,
    ):
        self.name = name
        self.limiter = limiter
        self.breaker = breaker
        self.retry_policy = retry_policy
        self.budget = budget
        self.max_wait_seconds = max_wait_seconds

    @classmethod
    def from_config(
        cls,
        name: str,
        requests_per_minute: int,
        market: MarketConfig,
        *,
        max_requests_per_day: int | None = None,
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
            budget=UsageBudget(max_requests_per_day) if max_requests_per_day else None,
            max_wait_seconds=market.max_queue_wait_seconds,
        )

    @property
    def state(self) -> BreakerState:
        return self.breaker.state

    async def call(self, operation: str, fn: Callable[[], Awaitable[T]]) -> T:
        if not self.breaker.allow_request():
            raise CircuitOpen(self.name, "temporarily skipped after repeated failures")

        async def attempt() -> T:
            # Fail fast when the budget is spent; count the call only once it may go out.
            # Every HTTP attempt, retries included, counts against the budget.
            if self.budget is not None and self.budget.remaining <= 0:
                raise ProviderQuotaExceeded(self.name, "daily request budget used up")
            try:
                await self.limiter.acquire(self.max_wait_seconds)
            except WaitTooLong as error:
                raise ProviderQuotaExceeded(self.name, "too many requests queued") from error
            if self.budget is not None and not self.budget.try_consume():
                raise ProviderQuotaExceeded(self.name, "daily request budget used up")
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
