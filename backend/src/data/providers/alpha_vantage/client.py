"""Alpha Vantage provider: index quotes and reference data (MD-03)."""

from __future__ import annotations

from typing import Any

import httpx

from src.core.config.settings import AlphaVantageConfig
from src.core.domain.market import IndexQuote, ReferenceData
from src.core.errors import ProviderBadResponse
from src.data.providers.alpha_vantage.parsers import (
    PROVIDER,
    parse_company_overview,
    parse_etf_profile,
    parse_global_quote,
)
from src.data.providers.http import get_json
from src.data.resilience.circuit_breaker import BreakerState
from src.data.resilience.guard import ProviderGuard


class AlphaVantageProvider:
    name = PROVIDER

    def __init__(
        self,
        client: httpx.AsyncClient,
        config: AlphaVantageConfig,
        guard: ProviderGuard,
        api_key: str,
    ):
        self._client = client
        self._config = config
        self._guard = guard
        self._api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    @property
    def breaker_state(self) -> BreakerState:
        return self._guard.state

    async def _query(self, operation: str, params: dict[str, Any]) -> Any:
        full = {**params, "apikey": self._api_key}
        return await self._guard.call(
            operation, lambda: get_json(self._client, self.name, self._config.base_url, params=full)
        )

    async def get_index_quote(self, index_id: str, name: str, symbol: str) -> IndexQuote:
        payload = await self._query("index_quote", {"function": "GLOBAL_QUOTE", "symbol": symbol})
        return parse_global_quote(index_id, name, symbol, payload)

    async def get_reference_data(self, symbol: str) -> ReferenceData:
        """Try the company overview first; fall back to the ETF profile for funds."""
        overview = await self._query("overview", {"function": "OVERVIEW", "symbol": symbol})
        reference = parse_company_overview(symbol, overview)
        if reference is not None:
            return reference
        profile = await self._query("etf_profile", {"function": "ETF_PROFILE", "symbol": symbol})
        reference = parse_etf_profile(symbol, profile)
        if reference is None:
            raise ProviderBadResponse(self.name, f"no reference data for {symbol}")
        return reference
