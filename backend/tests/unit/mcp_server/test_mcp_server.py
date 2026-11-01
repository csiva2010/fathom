"""MCP tools and their REST client, with the API mocked by respx (MCP-01, MCP-04)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import httpx
import pytest
import respx
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, Tool

from src.mcp_server import __main__ as entry
from src.mcp_server.api_client import ApiConfig, ApiError, FinanceApi
from src.mcp_server.server import DISCLAIMER, add_months, build_server

BASE = "http://api.test/api/v1"
TODAY = date(2026, 11, 1)
FRESH = {"source": "alpaca", "as_of": "2026-11-01T15:00:00Z", "status": "live"}


def envelope(status: int, message: str) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": "x", "message": message, "retryable": False}}
    )


@pytest.fixture
def api_mock() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


class McpSession:
    """Connects in-process per call: an async fixture can't hold the client's task group
    open across pytest-asyncio's setup and teardown tasks."""

    def __init__(self, server: MCPServer):
        self._server = server

    async def call_tool(self, name: str, args: dict[str, Any]) -> CallToolResult:
        async with Client(self._server) as client:
            return await client.call_tool(name, args)

    async def list_tools(self) -> list[Tool]:
        async with Client(self._server) as client:
            return (await client.list_tools()).tools


@pytest.fixture
def client(api_mock: respx.MockRouter) -> McpSession:
    return McpSession(build_server(FinanceApi(ApiConfig(BASE, "fa_pat_test")), today=TODAY))


async def call(client: McpSession, tool: str, args: dict[str, Any] | None = None) -> Any:
    result = await client.call_tool(tool, args or {})
    assert not result.is_error, result.content
    return result.structured_content


async def error_of(client: McpSession, tool: str, args: dict[str, Any] | None = None) -> str:
    result = await client.call_tool(tool, args or {})
    assert result.is_error
    text: str = result.content[0].text  # type: ignore[union-attr]
    return text


# --- Tool catalogue --------------------------------------------------------------------------


async def test_every_tool_is_read_only_and_carries_the_disclaimer(client: McpSession) -> None:
    tools = {t.name: t for t in await client.list_tools()}
    assert set(tools) == {
        "get_quote",
        "get_market_overview",
        "list_portfolios",
        "analyze_portfolio",
        "project_goal",
        "search_knowledge_base",
        "explain_term",
    }
    for name, tool in tools.items():
        assert tool.annotations is not None and tool.annotations.read_only_hint, name
        if name != "list_portfolios":
            assert DISCLAIMER in (tool.description or ""), name
    assert tools["get_quote"].input_schema["required"] == ["symbols"]


# --- Market ----------------------------------------------------------------------------------


async def test_get_quote_sends_the_token_and_joins_symbols(
    client: McpSession, api_mock: respx.MockRouter
) -> None:
    route = api_mock.get("/market/quotes").respond(
        json={"quotes": [{"quote": {"symbol": "AAPL"}, "freshness": FRESH}], "unknown_symbols": []}
    )
    result = await call(client, "get_quote", {"symbols": ["AAPL", " vti "]})
    assert result["quotes"][0]["freshness"]["status"] == "live"
    request = route.calls.last.request
    assert request.url.params["symbols"] == "AAPL,vti"
    assert request.headers["authorization"] == "Bearer fa_pat_test"


async def test_market_overview_combines_three_calls(
    client: McpSession, api_mock: respx.MockRouter
) -> None:
    api_mock.get("/market/overview").respond(json={"indices": [{"index": {"id": "SPX"}}]})
    api_mock.get("/market/sectors").respond(json={"sectors": [{"sector": {"symbol": "XLK"}}]})
    api_mock.get("/market/movers").respond(json={"gainers": [], "losers": []})
    result = await call(client, "get_market_overview")
    assert result == {
        "indices": [{"index": {"id": "SPX"}}],
        "sectors": [{"sector": {"symbol": "XLK"}}],
        "movers": {"gainers": [], "losers": []},
    }


# --- Portfolios ------------------------------------------------------------------------------

LISTING = {
    "portfolios": [
        {
            "id": "mine",
            "name": "My mix",
            "is_sample": False,
            "description": "",
            "holdings": [{"symbol": "VTI", "quantity": 5, "cost_basis": None}],
        },
        {"id": "s1", "name": "Three-Fund", "is_sample": True, "description": "", "holdings": []},
    ]
}
ANALYSIS = {"total_value": 1000, "benchmark": {"range": "1Y"}, "performance": [{"p": 1}] * 50}


async def test_list_portfolios_trims_to_ids_and_holdings(
    client: McpSession, api_mock: respx.MockRouter
) -> None:
    api_mock.get("/portfolios").respond(json=LISTING)
    result = await call(client, "list_portfolios")
    assert result["portfolios"][0] == {
        "id": "mine",
        "name": "My mix",
        "is_sample": False,
        "holdings": [{"symbol": "VTI", "quantity": 5}],
    }


async def test_analyze_defaults_to_the_latest_saved_portfolio(
    client: McpSession, api_mock: respx.MockRouter
) -> None:
    api_mock.get("/portfolios").respond(json=LISTING)
    route = api_mock.get("/portfolios/mine/analysis").respond(json=ANALYSIS)
    result = await call(client, "analyze_portfolio")
    assert result["portfolio_name"] == "My mix" and result["total_value"] == 1000
    assert "performance" not in result  # the daily series is dropped
    assert route.calls.last.request.url.params["range"] == "1Y"


async def test_analyze_by_id_or_inline_holdings(
    client: McpSession, api_mock: respx.MockRouter
) -> None:
    api_mock.get("/portfolios/s1/analysis").respond(json=ANALYSIS)
    by_id = await call(client, "analyze_portfolio", {"portfolio_id": "s1", "benchmark_range": "5Y"})
    assert "portfolio_name" not in by_id

    inline = api_mock.post("/portfolios/analyze").respond(json=ANALYSIS)
    holdings = [{"symbol": "VTI", "quantity": 3, "cost_basis": 200}]
    await call(client, "analyze_portfolio", {"holdings": holdings, "benchmark_range": "6M"})
    assert inline.calls.last.request.read() == (
        b'{"holdings":[{"symbol":"VTI","quantity":3.0,"cost_basis":200.0}],"range":"6M"}'
    )


async def test_analyze_argument_errors(client: McpSession, api_mock: respx.MockRouter) -> None:
    both = {"portfolio_id": "s1", "holdings": [{"symbol": "VTI", "quantity": 1}]}
    assert "not both" in await error_of(client, "analyze_portfolio", both)

    api_mock.get("/portfolios").respond(json={"portfolios": LISTING["portfolios"][1:]})
    assert "no saved portfolio" in await error_of(client, "analyze_portfolio")

    api_mock.post("/portfolios/analyze").mock(
        return_value=envelope(422, "We couldn't find ZZZZ. US stocks and ETFs only.")
    )
    message = await error_of(
        client, "analyze_portfolio", {"holdings": [{"symbol": "ZZZZ", "quantity": 1}]}
    )
    assert "couldn't find ZZZZ" in message


# --- Goals -----------------------------------------------------------------------------------

PROJECTION = {
    "projection": {"scenarios": [{"scenario": "expected"}], "series": [{"month": 0}] * 10},
    "example_allocation": {"risk_profile": "moderate"},
}


async def test_project_goal_from_years_uses_the_saved_risk_profile(
    client: McpSession, api_mock: respx.MockRouter
) -> None:
    api_mock.get("/me").respond(json={"profile": {"risk_profile": "aggressive"}})
    route = api_mock.post("/goals/project").respond(json=PROJECTION)
    result = await call(
        client, "project_goal", {"target_amount": 50000, "years": 2.5, "monthly_contribution": 300}
    )
    assert "series" not in result["projection"]
    sent = route.calls.last.request.read()
    assert b'"target_date":"2029-05-01"' in sent and b'"risk_profile":"aggressive"' in sent


async def test_project_goal_with_a_date_and_profile_skips_the_profile_lookup(
    client: McpSession, api_mock: respx.MockRouter
) -> None:
    me = api_mock.get("/me").respond(json={"profile": {"risk_profile": None}})
    route = api_mock.post("/goals/project").respond(json=PROJECTION)
    args = {"target_amount": 1000, "target_date": "2030-01-15", "risk_profile": "conservative"}
    await call(client, "project_goal", args)
    assert not me.called
    assert b'"target_date":"2030-01-15"' in route.calls.last.request.read()

    await call(client, "project_goal", {"target_amount": 1000, "years": 1})
    assert b'"risk_profile":"moderate"' in route.calls.last.request.read()  # none saved


async def test_project_goal_needs_exactly_one_horizon(client: McpSession) -> None:
    assert "exactly one" in await error_of(client, "project_goal", {"target_amount": 1})
    both = {"target_amount": 1, "years": 1, "target_date": "2030-01-01"}
    assert "exactly one" in await error_of(client, "project_goal", both)


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2027, 12, 15), 12) == date(2028, 12, 15)


# --- Knowledge base --------------------------------------------------------------------------


async def test_search_knowledge_base_passes_the_category(
    client: McpSession, api_mock: respx.MockRouter
) -> None:
    route = api_mock.get("/kb/search").respond(
        json={"query": "q", "mode": "keyword", "results": []}
    )
    await call(client, "search_knowledge_base", {"query": "roth ira", "category": "tax"})
    assert dict(route.calls.last.request.url.params) == {"q": "roth ira", "category": "tax"}
    await call(client, "search_knowledge_base", {"query": "roth ira"})
    assert dict(route.calls.last.request.url.params) == {"q": "roth ira"}


async def test_explain_term_quotes_the_path(client: McpSession, api_mock: respx.MockRouter) -> None:
    api_mock.get("/kb/glossary/expense%20ratio%2Ffee").respond(json={"term": "Expense ratio"})
    assert (await call(client, "explain_term", {"term": "expense ratio/fee"}))["term"] == (
        "Expense ratio"
    )
    api_mock.get("/kb/glossary/zebra").mock(
        return_value=envelope(404, "'zebra' isn't in the glossary.")
    )
    assert "isn't in the glossary" in await error_of(client, "explain_term", {"term": "zebra"})


# --- REST client errors and config -----------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "side_effect", "expected"),
    [
        (httpx.Response(401), None, "access token was rejected"),
        (httpx.Response(500, text="boom"), None, "returned HTTP 500"),
        (None, httpx.ConnectError("refused"), "Couldn't reach the Finance Assistant API at"),
        (None, httpx.ReadTimeout("slow"), "took too long"),
    ],
)
async def test_api_errors_become_readable_messages(
    api_mock: respx.MockRouter,
    response: httpx.Response | None,
    side_effect: Exception | None,
    expected: str,
) -> None:
    api_mock.get("/me").mock(return_value=response, side_effect=side_effect)
    api = FinanceApi(ApiConfig(BASE, "t"))
    with pytest.raises(ApiError, match=expected):
        await api.get("me")
    await api.aclose()


async def test_empty_responses_return_none(api_mock: respx.MockRouter) -> None:
    api_mock.post("/thing").respond(204)
    api = FinanceApi(ApiConfig(BASE, "t"))
    assert await api.post("thing", {}) is None
    await api.aclose()


def test_config_from_env() -> None:
    config = ApiConfig.from_env(
        {"FINANCE_API_URL": " https://x.test/api/v1/ ", "FINANCE_API_TOKEN": "t"}
    )
    assert config == ApiConfig("https://x.test/api/v1", "t")
    with pytest.raises(ValueError, match="FINANCE_API_URL and FINANCE_API_TOKEN"):
        ApiConfig.from_env({})
    with pytest.raises(ValueError, match="must start with http"):
        ApiConfig.from_env({"FINANCE_API_URL": "x.test", "FINANCE_API_TOKEN": "t"})


def test_main_reports_missing_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("FINANCE_API_URL", raising=False)
    monkeypatch.delenv("FINANCE_API_TOKEN", raising=False)
    assert entry.main() == 2
    assert "Set FINANCE_API_URL and FINANCE_API_TOKEN" in capsys.readouterr().err


def test_main_runs_the_server_over_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    runs: list[str] = []

    class FakeServer:
        def run(self, transport: str) -> None:
            runs.append(transport)

    monkeypatch.setenv("FINANCE_API_URL", BASE)
    monkeypatch.setenv("FINANCE_API_TOKEN", "t")
    monkeypatch.setattr(entry, "build_server", lambda api: FakeServer())
    assert entry.main() == 0 and runs == ["stdio"]
