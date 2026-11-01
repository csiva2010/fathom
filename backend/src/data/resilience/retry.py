"""Retry with exponential backoff and full jitter (MD-06).

Retries only errors marked `retryable` (timeouts, 429, 5xx). Auth errors and other 4xx
fail immediately.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from src.core.errors import AppError
from src.data.resilience import clock as default_clock

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 4.0

    def delay_for(self, attempt: int, rng: Callable[[], float] = random.random) -> float:
        """Full-jitter delay before retry number `attempt` (1-based)."""
        ceiling = min(self.max_delay, self.base_delay * 2.0 ** (attempt - 1))
        return ceiling * rng()


def is_retryable(error: BaseException) -> bool:
    return isinstance(error, AppError) and error.retryable


async def with_retry(
    call: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    *,
    sleep: default_clock.Sleeper = default_clock.sleep,
    rng: Callable[[], float] = random.random,
) -> T:
    attempt = 1
    while True:
        try:
            return await call()
        except Exception as error:
            if attempt >= policy.attempts or not is_retryable(error):
                raise
            await sleep(policy.delay_for(attempt, rng))
            attempt += 1
