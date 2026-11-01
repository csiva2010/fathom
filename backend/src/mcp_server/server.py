"""The finance tools Claude Desktop sees (MCP-01).

Each tool is one or two REST calls; the numbers come from the backend's services, so they
match the web app and the chat agents (MCP-02). Long chart series are dropped from tool
results to save the model's context: the summaries carry the same conclusions.
"""

from __future__ import annotations

import asyncio
import calendar
from collections.abc import Awaitable
from datetime import date
from typing import Annotated, Any, Literal, TypeVar
from urllib.parse import quote

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from src.mcp_server.api_client import ApiError, FinanceApi

T = TypeVar("T")

DISCLAIMER = "Educational information only, not investment advice."
MAX_QUOTE_SYMBOLS = 20

INSTRUCTIONS = f"""Tools from Fathom, the AI Finance Assistant: an educational finance app.
{DISCLAIMER} Explain numbers and concepts; never tell the user to buy, sell or hold a
specific security. Every market number carries `freshness` (source, as_of, and whether it
is live, cached or mock sample data): mention it, and say clearly when data is mock or
cached. Cite knowledge-base answers with the article title and source_url returned."""

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

RiskProfileArg = Literal["conservative", "moderate", "aggressive"]
RangeArg = Literal["1M", "3M", "6M", "1Y", "5Y"]


class HoldingArg(BaseModel):
    symbol: str = Field(min_length=1, max_length=10, description="US stock or ETF ticker, e.g. VTI")
    quantity: float = Field(gt=0, description="Number of shares")
    cost_basis: float | None = Field(default=None, ge=0, description="Average cost per share")


async def _call(request: Awaitable[T]) -> T:
    """Turn API failures into tool errors the model can read and act on."""
    try:
        return await request
    except ApiError as error:
        raise ToolError(str(error)) from error


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def build_server(api: FinanceApi, today: date | None = None) -> MCPServer:
    server: MCPServer = MCPServer(name="finance-assistant", instructions=INSTRUCTIONS)

    @server.tool(annotations=READ_ONLY)
    async def get_quote(
        symbols: Annotated[
            list[str],
            Field(min_length=1, max_length=MAX_QUOTE_SYMBOLS, description="Tickers, e.g. ['AAPL']"),
        ],
    ) -> dict[str, Any]:
        """Latest price and daily change for US stocks and ETFs, with freshness.
        Educational information only, not investment advice."""
        result: dict[str, Any] = await _call(
            api.get("market/quotes", {"symbols": ",".join(s.strip() for s in symbols)})
        )
        return result

    @server.tool(annotations=READ_ONLY)
    async def get_market_overview() -> dict[str, Any]:
        """Major US indexes, sector moves (via sector ETFs) and today's biggest movers from a
        fixed list of liquid stocks and ETFs, with freshness.
        Educational information only, not investment advice."""
        indices, sectors, movers = await _call(
            asyncio.gather(
                api.get("market/overview"), api.get("market/sectors"), api.get("market/movers")
            )
        )
        return {
            "indices": indices["indices"],
            "sectors": sectors["sectors"],
            "movers": movers,
        }

    @server.tool(annotations=READ_ONLY)
    async def list_portfolios() -> dict[str, Any]:
        """The user's saved portfolios (newest first) and the read-only sample portfolios,
        with their holdings. Use an id from here with analyze_portfolio."""
        listing = await _call(api.get("portfolios"))
        return {
            "portfolios": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "is_sample": p["is_sample"],
                    "holdings": [
                        {"symbol": h["symbol"], "quantity": h["quantity"]} for h in p["holdings"]
                    ],
                }
                for p in listing["portfolios"]
            ]
        }

    @server.tool(annotations=READ_ONLY)
    async def analyze_portfolio(
        portfolio_id: Annotated[
            str | None, Field(description="A portfolio id from list_portfolios")
        ] = None,
        holdings: Annotated[
            list[HoldingArg] | None,
            Field(max_length=200, description="Holdings to analyze without saving them"),
        ] = None,
        benchmark_range: Annotated[
            RangeArg, Field(description="Window for the S&P 500 comparison")
        ] = "1Y",
    ) -> dict[str, Any]:
        """Value, gain, allocation by holding, asset class and sector, diversification score,
        fees, risk (volatility, beta, worst drop) and an S&P 500 comparison. Pass either
        portfolio_id or holdings; with neither, the user's most recently saved portfolio is
        used. Educational information only, not investment advice."""
        if portfolio_id and holdings:
            raise ToolError("Pass either portfolio_id or holdings, not both.")
        name: str | None = None
        if holdings:
            body = {"holdings": [h.model_dump() for h in holdings], "range": benchmark_range}
            analysis = await _call(api.post("portfolios/analyze", body))
        else:
            if not portfolio_id:
                listing = await _call(api.get("portfolios"))
                saved = [p for p in listing["portfolios"] if not p["is_sample"]]
                if not saved:
                    raise ToolError(
                        "The user has no saved portfolio. Pass holdings, or a sample's "
                        "portfolio_id from list_portfolios."
                    )
                portfolio_id, name = saved[0]["id"], saved[0]["name"]
            analysis = await _call(
                api.get(
                    f"portfolios/{quote(portfolio_id, safe='')}/analysis",
                    {"range": benchmark_range},
                )
            )
        analysis.pop("performance", None)  # daily chart series; `benchmark` summarises it
        if name:
            analysis["portfolio_name"] = name
        result: dict[str, Any] = analysis
        return result

    @server.tool(annotations=READ_ONLY)
    async def project_goal(
        target_amount: Annotated[float, Field(gt=0, description="Goal amount in dollars")],
        years: Annotated[
            float | None, Field(gt=0, le=70, description="Years until the goal")
        ] = None,
        target_date: Annotated[
            date | None, Field(description="Goal date (YYYY-MM-DD), instead of years")
        ] = None,
        current_savings: Annotated[float, Field(ge=0)] = 0,
        monthly_contribution: Annotated[float, Field(ge=0)] = 0,
        risk_profile: Annotated[
            RiskProfileArg | None,
            Field(description="Defaults to the user's saved risk profile, else moderate"),
        ] = None,
    ) -> dict[str, Any]:
        """Project savings toward a goal under pessimistic, expected and optimistic return
        scenarios for a risk profile, with the monthly contribution each scenario needs and
        a generic textbook allocation for that profile. Illustrations, not predictions.
        Educational information only, not investment advice."""
        if (years is None) == (target_date is None):
            raise ToolError("Pass exactly one of years or target_date.")
        if target_date is None:
            assert years is not None
            target_date = add_months(today or date.today(), max(1, round(years * 12)))
        if risk_profile is None:
            me = await _call(api.get("me"))
            risk_profile = me["profile"]["risk_profile"] or "moderate"
        body = {
            "target_amount": target_amount,
            "target_date": target_date.isoformat(),
            "current_savings": current_savings,
            "monthly_contribution": monthly_contribution,
            "risk_profile": risk_profile,
        }
        result: dict[str, Any] = await _call(api.post("goals/project", body))
        result["projection"].pop("series", None)  # chart points; `scenarios` summarise them
        return result

    @server.tool(annotations=READ_ONLY)
    async def search_knowledge_base(
        query: Annotated[str, Field(min_length=1, max_length=500)],
        category: Annotated[
            str | None,
            Field(
                description=(
                    "Optional filter: basics, stocks, bonds, funds_etfs, retirement, tax, "
                    "risk_diversification, budgeting_saving, market_mechanics, "
                    "behavioral_finance"
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Search the app's curated financial-education articles. Returns the most relevant
        passages with their article title, section and source URL to cite. An empty result
        means the knowledge base has nothing relevant.
        Educational information only, not investment advice."""
        params = {"q": query} | ({"category": category} if category else {})
        result: dict[str, Any] = await _call(api.get("kb/search", params))
        return result

    @server.tool(annotations=READ_ONLY)
    async def explain_term(
        term: Annotated[
            str, Field(min_length=1, max_length=80, description="e.g. 'expense ratio'")
        ],
    ) -> dict[str, Any]:
        """Plain-language definition of a finance term from the app's glossary, with related
        terms. Educational information only, not investment advice."""
        result: dict[str, Any] = await _call(api.get(f"kb/glossary/{quote(term, safe='')}"))
        return result

    return server
