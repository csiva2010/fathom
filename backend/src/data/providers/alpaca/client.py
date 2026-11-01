"""Alpaca market-data provider: quotes, price bars, news and the symbol list
(MD-01, MD-02, MD-09, MD-10).

Data only (AS-07). The one call to the Trading API host is the read-only assets list used
for ticker search; nothing touches orders, positions or accounts.
"""

from __future__ import annotations

from datetime import datetime
from functools import partial
from typing import Any

import httpx

from src.core.config.settings import AlpacaConfig
from src.core.domain.market import Bar, NewsItem, Quote, SymbolInfo
from src.data.providers.alpaca.parsers import (
    parse_assets,
    parse_bars,
    parse_news,
    parse_snapshots,
)
from src.data.providers.http import get_json
from src.data.resilience.circuit_breaker import BreakerState
from src.data.resilience.guard import ProviderGuard

MAX_SYMBOLS_PER_REQUEST = 100
MAX_PAGES = 20
PAPER_ASSETS_URL = "https://paper-api.alpaca.markets"
LIVE_ASSETS_URL = "https://api.alpaca.markets"


class AlpacaProvider:
    name = "alpaca"

    def __init__(
        self,
        client: httpx.AsyncClient,
        config: AlpacaConfig,
        guard: ProviderGuard,
        key_id: str,
        secret_key: str,
    ):
        self._client = client
        self._config = config
        self._guard = guard
        self._key_id = key_id
        self._secret_key = secret_key

    @property
    def configured(self) -> bool:
        return bool(self._key_id and self._secret_key)

    @property
    def breaker_state(self) -> BreakerState:
        return self._guard.state

    @property
    def assets_base_url(self) -> str:
        if self._config.assets_base_url:
            return self._config.assets_base_url
        # Alpaca paper-account key ids start with "PK"; they are rejected by the live host.
        return PAPER_ASSETS_URL if self._key_id.startswith("PK") else LIVE_ASSETS_URL

    def _headers(self) -> dict[str, str]:
        return {"APCA-API-KEY-ID": self._key_id, "APCA-API-SECRET-KEY": self._secret_key}

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self._config.data_base_url}{path}"
        return await get_json(self._client, self.name, url, params=params, headers=self._headers())

    # --- Quotes ----------------------------------------------------------

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        quotes: dict[str, Quote] = {}
        for start in range(0, len(symbols), MAX_SYMBOLS_PER_REQUEST):
            batch = symbols[start : start + MAX_SYMBOLS_PER_REQUEST]
            params = {"symbols": ",".join(batch), "feed": self._config.feed}
            payload = await self._guard.call(
                "snapshots", partial(self._get, "/v2/stocks/snapshots", params)
            )
            quotes.update(parse_snapshots(payload))
        return quotes

    # --- Bars ------------------------------------------------------------

    async def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime | None = None
    ) -> list[Bar]:
        params: dict[str, Any] = {
            "timeframe": timeframe,
            "start": start.isoformat(),
            "adjustment": "all",
            "feed": self._config.feed,
            "limit": 10_000,
        }
        if end is not None:
            params["end"] = end.isoformat()

        bars: list[Bar] = []
        for _ in range(MAX_PAGES):
            payload = await self._guard.call(
                "bars", partial(self._get, f"/v2/stocks/{symbol}/bars", dict(params))
            )
            bars.extend(parse_bars(payload.get("bars") or []))
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        return bars

    # --- News ------------------------------------------------------------

    async def get_news(self, symbols: list[str], limit: int = 10) -> list[NewsItem]:
        params: dict[str, Any] = {"limit": limit, "sort": "desc"}
        if symbols:
            params["symbols"] = ",".join(symbols)
        payload = await self._guard.call("news", lambda: self._get("/v1beta1/news", params))
        return parse_news(payload)

    # --- Symbol list -----------------------------------------------------

    async def list_symbols(self) -> list[SymbolInfo]:
        url = f"{self.assets_base_url}/v2/assets"
        params = {"status": "active", "asset_class": "us_equity"}
        payload = await self._guard.call(
            "assets",
            lambda: get_json(self._client, self.name, url, params=params, headers=self._headers()),
        )
        return parse_assets(payload)
