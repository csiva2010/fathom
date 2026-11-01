"""Pure functions that turn Alpaca market-data JSON into domain models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.core.domain.market import Bar, NewsItem, Quote, SymbolInfo
from src.core.errors import ProviderBadResponse


def parse_timestamp(raw: str) -> datetime:
    # Alpaca returns RFC 3339 with nanoseconds and a trailing Z; trim to microseconds.
    value = raw.replace("Z", "+00:00")
    if "." in value:
        head, rest = value.split(".", 1)
        frac, sep, tz = rest.partition("+") if "+" in rest else rest.partition("-")
        value = f"{head}.{frac[:6]}{sep}{tz}"
    return datetime.fromisoformat(value)


def parse_snapshot(symbol: str, snapshot: dict[str, Any]) -> Quote | None:
    trade = snapshot.get("latestTrade") or {}
    daily = snapshot.get("dailyBar") or {}
    prev = snapshot.get("prevDailyBar") or {}

    price = trade.get("p") or daily.get("c")
    if price is None:
        return None
    timestamp = trade.get("t") or daily.get("t")
    previous_close = prev.get("c")
    change = price - previous_close if previous_close else None
    change_percent = (
        (change / previous_close * 100) if change is not None and previous_close else None
    )

    return Quote(
        symbol=symbol,
        price=float(price),
        previous_close=previous_close,
        change=round(change, 4) if change is not None else None,
        change_percent=round(change_percent, 4) if change_percent is not None else None,
        open=daily.get("o"),
        high=daily.get("h"),
        low=daily.get("l"),
        volume=daily.get("v"),
        as_of=parse_timestamp(timestamp) if timestamp else datetime.now().astimezone(),
    )


def parse_snapshots(payload: dict[str, Any]) -> dict[str, Quote]:
    quotes: dict[str, Quote] = {}
    for symbol, snapshot in payload.items():
        if isinstance(snapshot, dict):
            quote = parse_snapshot(symbol, snapshot)
            if quote is not None:
                quotes[symbol] = quote
    return quotes


def parse_bars(raw_bars: list[dict[str, Any]]) -> list[Bar]:
    return [
        Bar(
            t=parse_timestamp(b["t"]),
            open=b["o"],
            high=b["h"],
            low=b["l"],
            close=b["c"],
            volume=int(b.get("v", 0)),
        )
        for b in raw_bars
    ]


def parse_news(payload: dict[str, Any]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for article in payload.get("news", []):
        items.append(
            NewsItem(
                id=str(article["id"]),
                headline=article.get("headline", ""),
                summary=article.get("summary", ""),
                source=article.get("source", ""),
                url=article.get("url", ""),
                symbols=article.get("symbols", []),
                published_at=parse_timestamp(article["created_at"]),
            )
        )
    return items


# Listed US venues only; OTC and crypto are out of scope (AS-01).
LISTED_EXCHANGES = frozenset({"NYSE", "NASDAQ", "ARCA", "AMEX", "BATS", "NYSEARCA"})


def parse_assets(payload: Any) -> list[SymbolInfo]:
    if not isinstance(payload, list):
        raise ProviderBadResponse("alpaca", "unexpected assets response shape")
    symbols: list[SymbolInfo] = []
    for asset in payload:
        if not isinstance(asset, dict) or asset.get("status", "active") != "active":
            continue
        exchange = str(asset.get("exchange", "")).upper()
        symbol = str(asset.get("symbol", "")).upper()
        if symbol and exchange in LISTED_EXCHANGES:
            symbols.append(
                SymbolInfo(symbol=symbol, name=asset.get("name") or "", exchange=exchange)
            )
    return symbols
