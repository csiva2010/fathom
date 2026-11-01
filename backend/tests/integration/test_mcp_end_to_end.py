"""MCP server against the real FastAPI app, authenticated with a token from the API (MCP-02).

The MCP server's HTTP client is routed into the TestClient, so each tool call goes through
the real auth, routers and services, the same path Claude Desktop takes.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi.testclient import TestClient
from mcp import Client

from src.mcp_server.api_client import ApiConfig, FinanceApi
from src.mcp_server.server import build_server
from tests.integration.api.test_views_api import seed_sample, with_kb

API = "/api/v1"


class AppTransport(httpx.AsyncBaseTransport):
    """Hands each request to the (synchronous) TestClient, which runs the app."""

    def __init__(self, client: TestClient):
        self._client = client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = self._client.request(
            request.method,
            str(request.url),
            headers=dict(request.headers),
            content=request.read(),
        )
        return httpx.Response(
            response.status_code, headers=response.headers, content=response.content
        )


async def call(server: Any, tool: str, args: dict[str, Any]) -> Any:
    async with Client(server) as client:
        result = await client.call_tool(tool, args)
    return result


async def test_tools_reach_the_app_with_an_access_token(signed_in: TestClient) -> None:
    seed_sample(signed_in)
    with_kb(signed_in)
    token = signed_in.post(f"{API}/me/tokens", json={"name": "Claude Desktop"}).json()["token"]
    signed_in.cookies.clear()  # from here on only the token authenticates

    base_url = f"{signed_in.base_url}{API}"
    api = FinanceApi(ApiConfig(base_url, token), transport=AppTransport(signed_in))
    server = build_server(api)

    term = await call(server, "explain_term", {"term": "roth ira"})
    assert not term.is_error and term.structured_content["term"] == "Roth IRA"

    passages = await call(server, "search_knowledge_base", {"query": "roth ira"})
    assert passages.structured_content["results"][0]["citation"]["article_id"] == "roth-ira"

    projection = await call(server, "project_goal", {"target_amount": 20000, "years": 5})
    scenarios = projection.structured_content["projection"]["scenarios"]
    assert {s["scenario"] for s in scenarios} == {"pessimistic", "expected", "optimistic"}

    # No saved portfolio yet: the tool explains how to proceed instead of failing silently.
    missing = await call(server, "analyze_portfolio", {})
    assert missing.is_error and "no saved portfolio" in missing.content[0].text  # type: ignore[union-attr]

    analysis = await call(
        server, "analyze_portfolio", {"holdings": [{"symbol": "VTI", "quantity": 2}]}
    )
    assert analysis.structured_content["total_value"] > 0

    quotes = await call(server, "get_quote", {"symbols": ["AAPL"]})
    freshness = quotes.structured_content["quotes"][0]["freshness"]
    assert freshness["status"] in {"live", "cached", "mock"}
    await api.aclose()


async def test_a_revoked_token_gives_a_clear_tool_error(signed_in: TestClient) -> None:
    created = signed_in.post(f"{API}/me/tokens", json={"name": "old"}).json()
    signed_in.delete(f"{API}/me/tokens/{created['id']}")
    api = FinanceApi(
        ApiConfig(f"{signed_in.base_url}{API}", created["token"]),
        transport=AppTransport(signed_in),
    )
    result = await call(build_server(api), "explain_term", {"term": "roth ira"})
    assert result.is_error and "access token was rejected" in result.content[0].text  # type: ignore[union-attr]
    await api.aclose()
