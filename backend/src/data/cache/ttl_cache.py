"""In-process TTL cache with stale reads and request coalescing (MD-05).

Kept behind a small interface so a Redis implementation can replace it later.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from src.data.resilience import clock as default_clock

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    stored_at: datetime  # wall-clock time for freshness labels
    expires_at: float  # monotonic deadline

    def is_fresh(self, now: float) -> bool:
        return now < self.expires_at


class TTLCache:
    def __init__(
        self,
        *,
        max_entries: int = 10_000,
        clock: default_clock.Clock = default_clock.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._entries: dict[str, CacheEntry[Any]] = {}
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self._max_entries = max_entries
        self._clock = clock
        self._wall_clock = wall_clock

    def __len__(self) -> int:
        return len(self._entries)

    def get_fresh(self, key: str) -> CacheEntry[Any] | None:
        entry = self._entries.get(key)
        if entry is not None and entry.is_fresh(self._clock()):
            return entry
        return None

    def get_any(self, key: str) -> CacheEntry[Any] | None:
        """Return the entry even if expired; used as a fallback when providers fail."""
        return self._entries.get(key)

    def set(self, key: str, value: Any, ttl_seconds: float) -> CacheEntry[Any]:
        if len(self._entries) >= self._max_entries and key not in self._entries:
            self._evict_oldest()
        entry = CacheEntry(
            value=value,
            stored_at=self._wall_clock(),
            expires_at=self._clock() + ttl_seconds,
        )
        self._entries[key] = entry
        return entry

    def clear(self) -> None:
        self._entries.clear()

    def _evict_oldest(self) -> None:
        oldest = min(self._entries, key=lambda k: self._entries[k].expires_at)
        del self._entries[oldest]

    async def coalesce(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
        """Concurrent callers for the same key share one in-flight call."""
        pending = self._inflight.get(key)
        if pending is not None:
            return await asyncio.shield(pending)

        future: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            result = await factory()
        except BaseException as error:
            future.set_exception(error)
            # Mark retrieved so an un-awaited failure doesn't log "exception never retrieved".
            future.exception()
            raise
        else:
            future.set_result(result)
            return result
        finally:
            self._inflight.pop(key, None)
