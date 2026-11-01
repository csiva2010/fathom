from __future__ import annotations

import httpx
import pytest
import respx

from src.core.config.settings import AlphaVantageConfig
from src.core.domain.market import AssetClass
from src.core.errors import ProviderAuthError, ProviderBadResponse, ProviderRateLimited
from src.data.providers.alpha_vantage.client import AlphaVantageProvider
from src.data.providers.alpha_vantage.parsers import (
    check_payload,
    parse_company_overview,
    parse_etf_profile,
    parse_global_quote,
)
from src.data.resilience.circuit_breaker import BreakerState, CircuitBreaker
from src.data.resilience.guard import ProviderGuard
from src.data.resilience.rate_limiter import TokenBucket
from src.data.resilience.retry import RetryPolicy

URL = "https://www.alphavantage.co/query"

GLOBAL_QUOTE = {
    "Global Quote": {
        "01. symbol": "SPX",
        "05. price": "5800.1200",
        "07. latest trading day": "2026-10-29",
        "09. change": "12.5000",
        "10. change percent": "0.2160%",
    }
}


def make_provider(client: httpx.AsyncClient) -> AlphaVantageProvider:
    guard = ProviderGuard("alpha_vantage", TokenBucket(1000), CircuitBreaker(), RetryPolicy(1))
    return AlphaVantageProvider(client, AlphaVantageConfig(), guard, "key")


def test_check_payload_detects_errors_in_200_responses() -> None:
    with pytest.raises(ProviderBadResponse):
        check_payload({"Error Message": "Invalid API call"})
    with pytest.raises(ProviderRateLimited):
        check_payload({"Note": "Thank you for using Alpha Vantage! Our standard API rate limit..."})
    with pytest.raises(ProviderAuthError):
        check_payload({"Information": "The **demo** API key is invalid or missing."})
    with pytest.raises(ProviderBadResponse):
        check_payload(["not", "a", "dict"])
    assert check_payload({"ok": 1}) == {"ok": 1}


def test_parse_global_quote() -> None:
    quote = parse_global_quote("SPX", "S&P 500", "SPX", GLOBAL_QUOTE)
    assert quote.price == pytest.approx(5800.12)
    assert quote.change_percent == pytest.approx(0.216)
    assert quote.is_proxy is False
    assert quote.as_of.year == 2026


def test_parse_global_quote_empty_means_unsupported_symbol() -> None:
    with pytest.raises(ProviderBadResponse, match="no quote"):
        parse_global_quote("SPX", "S&P 500", "SPX", {"Global Quote": {}})
    quote = parse_global_quote(
        "X", "X", "X", {"Global Quote": {"05. price": "1", "09. change": "None"}}
    )
    assert quote.change is None


def test_parse_overview_and_etf_profile() -> None:
    overview = parse_company_overview(
        "AAPL",
        {"Symbol": "AAPL", "Name": "Apple", "Sector": "TECHNOLOGY", "Industry": "", "Beta": "1.2"},
    )
    assert overview is not None
    assert overview.asset_class is AssetClass.STOCK
    assert overview.industry is None
    assert overview.beta == 1.2
    assert parse_company_overview("VOO", {}) is None

    etf = parse_etf_profile(
        "VOO",
        {
            "net_expense_ratio": "0.0003",
            "sectors": [{"sector": "INFORMATION TECHNOLOGY", "weight": "0.31"}, {"sector": "x"}],
        },
    )
    assert etf is not None
    assert etf.expense_ratio == pytest.approx(0.0003)
    assert etf.sector_weights[0].sector == "Information Technology"
    assert len(etf.sector_weights) == 1
    assert parse_etf_profile("ZZZ", {}) is None
    assert parse_etf_profile("ZZZ", {"name": "x"}) is None


@respx.mock
async def test_index_quote_request() -> None:
    route = respx.get(URL).respond(200, json=GLOBAL_QUOTE)
    async with httpx.AsyncClient() as client:
        provider = make_provider(client)
        quote = await provider.get_index_quote("SPX", "S&P 500", "SPX")
    params = route.calls.last.request.url.params
    assert params["function"] == "GLOBAL_QUOTE"
    assert params["apikey"] == "key"
    assert quote.id == "SPX"
    assert provider.configured
    assert provider.breaker_state is BreakerState.CLOSED


@respx.mock
async def test_reference_data_falls_back_to_etf_profile() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        function = request.url.params["function"]
        if function == "OVERVIEW":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"net_expense_ratio": "0.0009", "sectors": []})

    respx.get(URL).mock(side_effect=respond)
    async with httpx.AsyncClient() as client:
        reference = await make_provider(client).get_reference_data("SPY")
    assert reference.asset_class is AssetClass.ETF


@respx.mock
async def test_reference_data_for_stock_and_unknown() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.params["symbol"] == "AAPL":
            return httpx.Response(200, json={"Symbol": "AAPL", "Name": "Apple"})
        return httpx.Response(200, json={})

    respx.get(URL).mock(side_effect=respond)
    async with httpx.AsyncClient() as client:
        provider = make_provider(client)
        assert (await provider.get_reference_data("AAPL")).name == "Apple"
        with pytest.raises(ProviderBadResponse):
            await provider.get_reference_data("ZZZZ")
