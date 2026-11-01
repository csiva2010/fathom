from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from src.core.domain.market import DataStatus
from src.core.errors import ProviderUnavailable, UnknownSymbol
from src.data.cache.ttl_cache import TTLCache
from src.data.providers.chain import ProviderChain, Source

WALL = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_cache(clock: Clock, **kwargs: int) -> TTLCache:
    return TTLCache(clock=clock, wall_clock=lambda: WALL, **kwargs)


# --- TTL cache -----------------------------------------------------------------


def test_cache_fresh_then_stale() -> None:
    clock = Clock()
    cache = make_cache(clock)
    cache.set("k", 1, ttl_seconds=10)
    assert cache.get_fresh("k") is not None
    clock.now = 11
    assert cache.get_fresh("k") is None
    stale = cache.get_any("k")
    assert stale is not None and stale.value == 1
    assert len(cache) == 1
    cache.clear()
    assert cache.get_any("k") is None


def test_cache_evicts_oldest_when_full() -> None:
    cache = make_cache(Clock(), max_entries=2)
    cache.set("a", 1, 10)
    cache.set("b", 2, 20)
    cache.set("c", 3, 30)
    assert cache.get_any("a") is None
    assert cache.get_any("c") is not None


async def test_cache_coalesces_concurrent_calls() -> None:
    cache = TTLCache()
    calls = 0

    async def slow() -> int:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return 7

    results = await asyncio.gather(*(cache.coalesce("k", slow) for _ in range(5)))
    assert results == [7] * 5
    assert calls == 1


async def test_cache_coalesce_propagates_errors_to_all_waiters() -> None:
    cache = TTLCache()

    async def boom() -> int:
        await asyncio.sleep(0.01)
        raise ProviderUnavailable("x", "down")

    results = await asyncio.gather(
        *(cache.coalesce("k", boom) for _ in range(3)), return_exceptions=True
    )
    assert all(isinstance(r, ProviderUnavailable) for r in results)


# --- Provider chain ------------------------------------------------------------


def ok(value: object):  # type: ignore[no-untyped-def]
    async def fetch() -> object:
        return value

    return fetch


def failing(error: Exception):  # type: ignore[no-untyped-def]
    async def fetch() -> object:
        raise error

    return fetch


async def test_chain_returns_live_then_cached() -> None:
    clock = Clock()
    chain = ProviderChain(make_cache(clock), wall_clock=lambda: WALL)
    live = await chain.resolve("k", 60, [Source("alpaca", ok(10))])
    assert live.value == 10
    assert live.freshness.status is DataStatus.LIVE
    assert live.freshness.source == "alpaca"

    cached = await chain.resolve("k", 60, [Source("alpaca", failing(AssertionError()))])
    assert cached.freshness.status is DataStatus.CACHED
    assert cached.freshness.source == "alpaca"


async def test_chain_falls_through_providers_in_order() -> None:
    chain = ProviderChain(TTLCache())
    result = await chain.resolve(
        "k",
        60,
        [
            Source("unconfigured", ok(1), configured=False),
            Source("down", failing(ProviderUnavailable("down", "x"))),
            Source("buggy", failing(KeyError("parse bug"))),
            Source("backup", ok(3)),
        ],
    )
    assert result.value == 3
    assert result.freshness.source == "backup"


async def test_chain_uses_stale_cache_before_mock() -> None:
    clock = Clock()
    chain = ProviderChain(make_cache(clock), wall_clock=lambda: WALL)
    await chain.resolve("k", 10, [Source("alpaca", ok("old"))])
    clock.now = 100
    result = await chain.resolve(
        "k", 10, [Source("alpaca", failing(ProviderUnavailable("a", "x")))], fallback=lambda: "mock"
    )
    assert result.value == "old"
    assert result.freshness.status is DataStatus.CACHED


async def test_chain_uses_mock_last() -> None:
    chain = ProviderChain(TTLCache())
    result = await chain.resolve(
        "k", 10, [Source("alpaca", failing(ProviderUnavailable("a", "x")))], fallback=lambda: "m"
    )
    assert result.value == "m"
    assert result.freshness.status is DataStatus.MOCK
    assert result.freshness.source == "mock"


async def test_chain_raises_when_nothing_answers() -> None:
    chain = ProviderChain(TTLCache())
    with pytest.raises(ProviderUnavailable):
        await chain.resolve("k", 10, [Source("a", failing(ProviderUnavailable("a", "x")))])
    with pytest.raises(ProviderUnavailable):
        await chain.resolve("k2", 10, [Source("a", failing(ValueError("bug")))])
    with pytest.raises(ProviderUnavailable):
        await chain.resolve("k3", 10, [])


async def test_chain_passes_definitive_errors_through() -> None:
    chain = ProviderChain(TTLCache())
    with pytest.raises(UnknownSymbol):
        await chain.resolve(
            "k", 10, [Source("a", failing(UnknownSymbol(["ZZZ"])))], fallback=lambda: "m"
        )
