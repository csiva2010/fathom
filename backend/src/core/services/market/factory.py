"""Wires providers, guards, cache and chain into a MarketDataService from Settings."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.core.config import Settings, resolve_path
from src.core.services.market.market_data_service import MarketDataService
from src.data.cache.ttl_cache import TTLCache
from src.data.providers.alpaca.client import AlpacaProvider
from src.data.providers.alpha_vantage.client import AlphaVantageProvider
from src.data.providers.chain import ProviderChain
from src.data.providers.mock.provider import MockMarketProvider
from src.data.providers.mock.seed_loader import SeedData
from src.data.resilience.guard import ProviderGuard


@dataclass(frozen=True)
class MarketProviders:
    alpaca: AlpacaProvider
    alpha_vantage: AlphaVantageProvider
    mock: MockMarketProvider


def build_providers(settings: Settings, http_client: httpx.AsyncClient) -> MarketProviders:
    market = settings.market
    return MarketProviders(
        alpaca=AlpacaProvider(
            client=http_client,
            config=market.alpaca,
            guard=ProviderGuard.from_config("alpaca", market.alpaca.requests_per_minute, market),
            key_id=settings.alpaca_api_key_id.get_secret_value(),
            secret_key=settings.alpaca_api_secret_key.get_secret_value(),
        ),
        alpha_vantage=AlphaVantageProvider(
            client=http_client,
            config=market.alpha_vantage,
            guard=ProviderGuard.from_config(
                "alpha_vantage", market.alpha_vantage.requests_per_minute, market
            ),
            api_key=settings.alpha_vantage_api_key.get_secret_value(),
        ),
        mock=MockMarketProvider(SeedData(resolve_path(settings.seed.dir))),
    )


def build_market_service(
    settings: Settings,
    http_client: httpx.AsyncClient,
    cache: TTLCache | None = None,
) -> MarketDataService:
    providers = build_providers(settings, http_client)
    return MarketDataService(
        chain=ProviderChain(cache or TTLCache()),
        alpaca=providers.alpaca,
        alpha_vantage=providers.alpha_vantage,
        mock=providers.mock,
        ttl=settings.market.cache_ttl_seconds,
        indices=settings.market.indices,
        sector_etfs=settings.market.sector_etfs,
        movers_universe=settings.market.movers_universe,
    )


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=settings.market.http_timeout_seconds)
