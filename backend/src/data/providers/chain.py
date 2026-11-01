"""ProviderChain: cache -> providers in order -> stale cache -> mock (MD-04, MD-05, MD-07).

Every value returned is stamped with Freshness so the UI can label it live/cached/mock.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from src.core.domain.market import DataStatus, Freshness, Sourced
from src.core.errors import AppError, ProviderError, ProviderUnavailable
from src.core.logging import get_logger
from src.data.cache.ttl_cache import TTLCache

T = TypeVar("T")
log = get_logger(__name__)

MOCK_SOURCE = "mock"


@dataclass(frozen=True)
class Source(Generic[T]):
    """One step in a chain: a named provider call."""

    name: str
    fetch: Callable[[], Awaitable[T]]
    configured: bool = True


@dataclass(frozen=True)
class _Cached:
    value: Any
    source: str


class ProviderChain:
    def __init__(
        self,
        cache: TTLCache,
        *,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.cache = cache
        self._now = wall_clock

    # --- Cache helpers (also used by batch callers such as quotes) -----------

    def cached_fresh(self, key: str) -> Sourced[Any] | None:
        entry = self.cache.get_fresh(key)
        return self._from_entry(entry) if entry else None

    def cached_any(self, key: str) -> Sourced[Any] | None:
        entry = self.cache.get_any(key)
        return self._from_entry(entry) if entry else None

    def store(self, key: str, value: T, source: str, ttl_seconds: float) -> Sourced[T]:
        self.cache.set(key, _Cached(value, source), ttl_seconds)
        return Sourced(
            value=value,
            freshness=Freshness(source=source, as_of=self._now(), status=DataStatus.LIVE),
        )

    def mock(self, value: T) -> Sourced[T]:
        return Sourced(
            value=value,
            freshness=Freshness(source=MOCK_SOURCE, as_of=self._now(), status=DataStatus.MOCK),
        )

    @staticmethod
    def _from_entry(entry: Any) -> Sourced[Any]:
        cached: _Cached = entry.value
        return Sourced(
            value=cached.value,
            freshness=Freshness(
                source=cached.source, as_of=entry.stored_at, status=DataStatus.CACHED
            ),
        )

    # --- Main entry point ----------------------------------------------------

    async def resolve(
        self,
        key: str,
        ttl_seconds: float,
        sources: list[Source[T]],
        fallback: Callable[[], T] | None = None,
    ) -> Sourced[T]:
        fresh = self.cached_fresh(key)
        if fresh is not None:
            return fresh

        async def fetch() -> Sourced[T]:
            last_error: Exception | None = None
            for source in sources:
                if not source.configured:
                    continue
                try:
                    value = await source.fetch()
                except ProviderError as error:
                    last_error = error
                    continue
                except AppError:
                    raise  # a definitive answer such as UnknownSymbol, not an outage
                except Exception as error:  # parsing bugs must degrade, not crash (OR-07)
                    log.exception("unexpected provider failure", extra={"provider": source.name})
                    last_error = error
                    continue
                return self.store(key, value, source.name, ttl_seconds)

            stale = self.cached_any(key)
            if stale is not None:
                return stale
            if fallback is not None:
                return self.mock(fallback())
            if isinstance(last_error, ProviderError):
                raise last_error
            raise ProviderUnavailable("market data", "no provider could answer") from last_error

        return await self.cache.coalesce(key, fetch)
