from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from src.core.config.settings import AlpacaConfig
from src.data.providers.alpaca.client import AlpacaProvider
from src.data.providers.alpaca.parsers import parse_snapshot, parse_timestamp
from src.data.resilience.circuit_breaker import BreakerState, CircuitBreaker
from src.data.resilience.guard import ProviderGuard
from src.data.resilience.rate_limiter import TokenBucket
from src.data.resilience.retry import RetryPolicy

BASE = "https://data.alpaca.markets"

SNAPSHOT = {
    "latestTrade": {"p": 101.0, "t": "2026-10-30T15:30:00.123456789Z"},
    "dailyBar": {
        "o": 99.0,
        "h": 102.0,
        "l": 98.5,
        "c": 100.5,
        "v": 1000,
        "t": "2026-10-30T04:00:00Z",
    },
    "prevDailyBar": {"c": 100.0},
}


def make_provider(client: httpx.AsyncClient, key: str = "k") -> AlpacaProvider:
    guard = ProviderGuard("alpaca", TokenBucket(1000), CircuitBreaker(), RetryPolicy(attempts=1))
    return AlpacaProvider(client, AlpacaConfig(feed="iex"), guard, key, "s")


def test_parse_timestamp_handles_nanoseconds_and_offsets() -> None:
    assert parse_timestamp("2026-10-30T15:30:00.123456789Z") == datetime(
        2026, 10, 30, 15, 30, 0, 123456, tzinfo=UTC
    )
    assert parse_timestamp("2026-10-30T15:30:00Z").tzinfo is not None
    assert parse_timestamp("2026-10-30T11:30:00.5-04:00").utcoffset() is not None


def test_parse_snapshot_computes_change() -> None:
    quote = parse_snapshot("AAPL", SNAPSHOT)
    assert quote is not None
    assert quote.price == 101.0
    assert quote.change == pytest.approx(1.0)
    assert quote.change_percent == pytest.approx(1.0)
    assert quote.volume == 1000


def test_parse_snapshot_without_price_or_previous_close() -> None:
    assert parse_snapshot("X", {}) is None
    quote = parse_snapshot("X", {"dailyBar": {"c": 5.0}})
    assert quote is not None and quote.change is None


@respx.mock
async def test_get_quotes_sends_keys_and_parses() -> None:
    route = respx.get(f"{BASE}/v2/stocks/snapshots").respond(
        200, json={"AAPL": SNAPSHOT, "BAD": None}
    )
    async with httpx.AsyncClient() as client:
        provider = make_provider(client)
        quotes = await provider.get_quotes(["AAPL", "ZZZZ"])

    assert list(quotes) == ["AAPL"]
    request = route.calls.last.request
    assert request.headers["APCA-API-KEY-ID"] == "k"
    assert request.url.params["symbols"] == "AAPL,ZZZZ"
    assert request.url.params["feed"] == "iex"
    assert provider.configured
    assert provider.breaker_state is BreakerState.CLOSED


@respx.mock
async def test_get_bars_follows_pagination() -> None:
    bar = {"t": "2026-10-29T04:00:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10}
    route = respx.get(f"{BASE}/v2/stocks/AAPL/bars")
    route.side_effect = [
        httpx.Response(200, json={"bars": [bar], "next_page_token": "abc"}),
        httpx.Response(200, json={"bars": [bar], "next_page_token": None}),
    ]
    async with httpx.AsyncClient() as client:
        bars = await make_provider(client).get_bars(
            "AAPL", "1Day", datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 30, tzinfo=UTC)
        )
    assert len(bars) == 2
    assert bars[0].low == 0.5
    assert route.calls[1].request.url.params["page_token"] == "abc"
    assert "end" in route.calls[0].request.url.params


@respx.mock
async def test_get_news_parses_items() -> None:
    respx.get(f"{BASE}/v1beta1/news").respond(
        200,
        json={
            "news": [
                {
                    "id": 1,
                    "headline": "Apple reports earnings",
                    "summary": "s",
                    "source": "benzinga",
                    "url": "https://x",
                    "symbols": ["AAPL"],
                    "created_at": "2026-10-30T12:00:00Z",
                }
            ]
        },
    )
    async with httpx.AsyncClient() as client:
        items = await make_provider(client).get_news(["AAPL"], limit=5)
        market = await make_provider(client).get_news([], limit=5)
    assert items[0].headline == "Apple reports earnings"
    assert items[0].id == "1"
    assert len(market) == 1


def test_unconfigured_without_keys() -> None:
    provider = make_provider(httpx.AsyncClient(), key="")
    assert not provider.configured
