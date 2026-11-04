from __future__ import annotations

import asyncio

import pytest

from src.core.config.settings import MarketConfig
from src.core.errors import (
    CircuitOpen,
    ProviderAuthError,
    ProviderBadResponse,
    ProviderQuotaExceeded,
    ProviderUnavailable,
)
from src.data.resilience.circuit_breaker import BreakerState, CircuitBreaker
from src.data.resilience.guard import ProviderGuard
from src.data.resilience.rate_limiter import TokenBucket, WaitTooLong
from src.data.resilience.retry import RetryPolicy, is_retryable, with_retry
from src.data.resilience.usage_budget import UsageBudget


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


# --- Token bucket ------------------------------------------------------------


async def test_token_bucket_allows_burst_then_waits() -> None:
    t = FakeTime()
    bucket = TokenBucket(rate_per_second=1, capacity=2, clock=t.clock, sleep=t.sleep)
    await bucket.acquire()
    await bucket.acquire()
    assert t.sleeps == []
    await bucket.acquire()
    assert t.sleeps == [pytest.approx(1.0)]


async def test_token_bucket_refills_over_time() -> None:
    t = FakeTime()
    bucket = TokenBucket(rate_per_second=2, capacity=2, clock=t.clock, sleep=t.sleep)
    await bucket.acquire()
    await bucket.acquire()
    t.now += 1.0
    assert bucket.available == pytest.approx(2.0)


def test_token_bucket_per_minute_and_validation() -> None:
    bucket = TokenBucket.per_minute(120)
    assert bucket.rate == pytest.approx(2.0)
    assert bucket.capacity == 120
    with pytest.raises(ValueError):
        TokenBucket(0)


async def test_token_bucket_queues_callers_by_reservation() -> None:
    t = FakeTime()
    bucket = TokenBucket(rate_per_second=1, capacity=1, clock=t.clock, sleep=t.sleep)
    await bucket.acquire()
    await bucket.acquire()
    assert t.sleeps == [pytest.approx(1.0)]
    assert bucket.available == pytest.approx(0.0)


async def test_token_bucket_refuses_callers_that_would_wait_too_long() -> None:
    t = FakeTime()
    sleeps: list[float] = []

    async def no_time_passes(seconds: float) -> None:
        sleeps.append(seconds)

    bucket = TokenBucket(rate_per_second=1, capacity=1, clock=t.clock, sleep=no_time_passes)
    await bucket.acquire(max_wait=2)
    await bucket.acquire(max_wait=2)  # waits 1s
    await bucket.acquire(max_wait=2)  # queued behind it: waits 2s
    with pytest.raises(WaitTooLong) as caught:
        await bucket.acquire(max_wait=2)
    assert caught.value.wait_seconds == pytest.approx(3.0)
    assert sleeps == [pytest.approx(1.0), pytest.approx(2.0)]
    assert bucket.available == pytest.approx(-2.0)  # the refused caller reserved nothing


# --- Usage budget ------------------------------------------------------------


def test_usage_budget_caps_calls_per_period_and_resets() -> None:
    t = FakeTime()
    t.now = 100.0
    budget = UsageBudget(2, period_seconds=1000, clock=t.clock)
    assert budget.try_consume()
    assert budget.try_consume()
    assert not budget.try_consume()
    assert budget.remaining == 0
    assert budget.resets_in == pytest.approx(900.0)

    t.now = 1000.0  # next period
    assert budget.remaining == 2
    assert budget.try_consume()
    assert budget.used == 1
    with pytest.raises(ValueError):
        UsageBudget(0)


# --- Retry -------------------------------------------------------------------


def test_retry_delay_grows_and_is_capped() -> None:
    policy = RetryPolicy(attempts=5, base_delay=0.5, max_delay=1.5)
    assert policy.delay_for(1, rng=lambda: 1.0) == 0.5
    assert policy.delay_for(2, rng=lambda: 1.0) == 1.0
    assert policy.delay_for(4, rng=lambda: 1.0) == 1.5
    assert policy.delay_for(4, rng=lambda: 0.0) == 0.0


async def test_retry_succeeds_after_transient_failures() -> None:
    t = FakeTime()
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ProviderUnavailable("x", "timeout")
        return "ok"

    assert await with_retry(flaky, RetryPolicy(attempts=3), sleep=t.sleep, rng=lambda: 1) == "ok"
    assert calls == 3
    assert len(t.sleeps) == 2


async def test_retry_gives_up_after_max_attempts() -> None:
    t = FakeTime()

    async def always_down() -> None:
        raise ProviderUnavailable("x", "down")

    with pytest.raises(ProviderUnavailable):
        await with_retry(always_down, RetryPolicy(attempts=2), sleep=t.sleep)
    assert len(t.sleeps) == 1


async def test_retry_never_retries_auth_errors() -> None:
    calls = 0

    async def bad_key() -> None:
        nonlocal calls
        calls += 1
        raise ProviderAuthError("x", "bad key")

    with pytest.raises(ProviderAuthError):
        await with_retry(bad_key, RetryPolicy(attempts=3))
    assert calls == 1
    assert not is_retryable(ValueError("plain"))


# --- Circuit breaker ---------------------------------------------------------


def test_breaker_opens_after_threshold_and_half_opens_after_reset() -> None:
    t = FakeTime()
    breaker = CircuitBreaker(failure_threshold=2, reset_seconds=60, clock=t.clock)
    breaker.record_failure()
    assert breaker.state is BreakerState.CLOSED
    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN
    assert not breaker.allow_request()

    t.now += 60
    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.allow_request()

    breaker.record_failure()  # trial failed: open again
    assert breaker.state is BreakerState.OPEN

    t.now += 60
    breaker.record_success()
    assert breaker.state is BreakerState.CLOSED
    assert breaker.consecutive_failures == 0


# --- Guard -------------------------------------------------------------------


def _guard(t: FakeTime, threshold: int = 2) -> ProviderGuard:
    return ProviderGuard(
        "fake",
        TokenBucket(100, clock=t.clock, sleep=t.sleep),
        CircuitBreaker(threshold, 60, clock=t.clock),
        RetryPolicy(attempts=1),
    )


async def test_guard_trips_breaker_on_outages_only() -> None:
    t = FakeTime()
    guard = _guard(t)

    async def outage() -> None:
        raise ProviderUnavailable("fake", "down")

    async def bad_request() -> None:
        raise ProviderBadResponse("fake", "unknown symbol")

    with pytest.raises(ProviderBadResponse):
        await guard.call("op", bad_request)
    assert guard.breaker.consecutive_failures == 0

    for _ in range(2):
        with pytest.raises(ProviderUnavailable):
            await guard.call("op", outage)
    assert guard.state is BreakerState.OPEN

    with pytest.raises(CircuitOpen):
        await guard.call("op", outage)


async def test_guard_success_resets_breaker() -> None:
    t = FakeTime()
    guard = _guard(t, threshold=5)

    async def ok() -> int:
        return 42

    guard.breaker.record_failure()
    assert await guard.call("op", ok) == 42
    assert guard.breaker.consecutive_failures == 0


async def test_guard_refuses_calls_once_the_budget_is_spent() -> None:
    t = FakeTime()
    guard = ProviderGuard(
        "fake",
        TokenBucket(100, clock=t.clock, sleep=t.sleep),
        CircuitBreaker(1, 60, clock=t.clock),
        RetryPolicy(attempts=3),
        budget=UsageBudget(3, clock=t.clock),
    )
    calls = 0

    async def flaky() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ProviderUnavailable("fake", "timeout")
        return calls

    assert await guard.call("op", flaky) == 2  # the retry counts against the budget too
    assert await guard.call("op", flaky) == 3
    with pytest.raises(ProviderQuotaExceeded, match="daily request budget"):
        await guard.call("op", flaky)
    assert calls == 3
    assert guard.state is BreakerState.CLOSED  # our own cap is not a provider outage


async def test_guard_refuses_calls_that_would_queue_too_long() -> None:
    t = FakeTime()
    budget = UsageBudget(10, clock=t.clock)
    guard = ProviderGuard(
        "fake",
        TokenBucket(rate_per_second=1, capacity=1, clock=t.clock, sleep=t.sleep),
        CircuitBreaker(1, 60, clock=t.clock),
        RetryPolicy(attempts=3),
        budget=budget,
        max_wait_seconds=0.5,
    )

    async def ok() -> int:
        return 1

    await guard.call("op", ok)
    with pytest.raises(ProviderQuotaExceeded, match="queued"):
        await guard.call("op", ok)
    assert budget.used == 1  # a refused call spends no budget
    assert guard.state is BreakerState.CLOSED


async def test_guard_rechecks_the_budget_after_queueing() -> None:
    t = FakeTime()

    async def yielding_sleep(seconds: float) -> None:
        await asyncio.sleep(0)  # let the other caller run while this one waits

    guard = ProviderGuard(
        "fake",
        TokenBucket(rate_per_second=1, capacity=1, clock=t.clock, sleep=yielding_sleep),
        CircuitBreaker(1, 60, clock=t.clock),
        RetryPolicy(attempts=1),
        budget=UsageBudget(2, clock=t.clock),
    )

    async def ok() -> int:
        return 1

    await guard.call("op", ok)  # empties the bucket; one budget unit left
    # Both pass the up-front check and queue; only the first to wake may spend it.
    results = await asyncio.gather(
        guard.call("op", ok), guard.call("op", ok), return_exceptions=True
    )
    assert results[0] == 1
    assert isinstance(results[1], ProviderQuotaExceeded)


def test_guard_from_config_uses_market_settings() -> None:
    market = MarketConfig.model_validate(
        {
            "retry": {"attempts": 4},
            "circuit_breaker": {"failure_threshold": 7},
            "max_queue_wait_seconds": 3,
        }
    )
    guard = ProviderGuard.from_config("alpaca", 60, market)
    assert guard.retry_policy.attempts == 4
    assert guard.breaker.failure_threshold == 7
    assert guard.limiter.rate == pytest.approx(1.0)
    assert guard.max_wait_seconds == 3
    assert guard.budget is None

    capped = ProviderGuard.from_config("alpaca", 60, market, max_requests_per_day=500)
    assert capped.budget is not None
    assert capped.budget.limit == 500
