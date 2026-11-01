"""Market Analysis agent (AG-03): quotes, trends and indices explained in plain language.

All numbers come from `MarketDataService` and carry Freshness (MD-07); the LLM only picks
extra tools and explains. With tickers in the plan, quotes and indicators are fetched up
front; without, the agent starts from the index overview and top movers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from src.agents.base_agent import AgentRun, AgentTool, BaseAgent, Prepared, as_data, to_json
from src.core.domain.market import (
    IndexQuote,
    Indicators,
    PriceRange,
    Quote,
    Sourced,
)
from src.core.errors import UnknownSymbol
from src.core.llm import LLMGateway
from src.core.services.indicators import percent_change
from src.core.services.market.market_data_service import MarketDataService
from src.utils.money import format_percent, format_usd
from src.workflow.state import AgentName, Artifact, FinanceState

MAX_TICKERS = 3


class QuotesArgs(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=5, description="US stock or ETF tickers")


class HistoryArgs(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    range: PriceRange = Field(default=PriceRange.Y1, description="1D, 5D, 1M, 3M, 6M, 1Y or 5Y")


class SymbolArgs(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)


class MoversArgs(BaseModel):
    limit: int = Field(default=5, ge=1, le=10)


class NoArgs(BaseModel):
    pass


def quote_facts(sourced: Sourced[Quote]) -> dict[str, Any]:
    q, f = sourced.value, sourced.freshness
    return {
        "symbol": q.symbol,
        "price": q.price,
        "change": q.change,
        "change_percent": q.change_percent,
        "previous_close": q.previous_close,
        "as_of": q.as_of.isoformat(),
        "source": f.source,
        "status": f.status.value,
    }


def indicator_facts(sourced: Sourced[Indicators]) -> dict[str, Any]:
    facts = sourced.value.model_dump(mode="json", exclude_none=True)
    facts["status"] = sourced.freshness.status.value
    return facts


def index_facts(sourced: Sourced[IndexQuote]) -> dict[str, Any]:
    i = sourced.value
    return {
        "name": i.name,
        "symbol": i.symbol,
        "is_etf_proxy": i.is_proxy,
        "price": i.price,
        "change_percent": i.change_percent,
        "status": sourced.freshness.status.value,
    }


def _signed(value: float | None) -> str:
    return format_percent(value, signed=True) if value is not None else "n/a"


class MarketAnalysisAgent(BaseAgent):
    name = AgentName.MARKET
    role_prompt = """You are the Market Analysis agent. You explain what market data \
shows: price moves, trends, moving averages, 52-week ranges, volatility, indices, sectors \
and movers.
- Use only the numbers in the market data and tool results. Mention when data is cached \
or mock (status field) rather than live.
- Interpret in plain language what each figure means (e.g. what trading above the 200-day \
average suggests about the trend), without predicting prices or recommending trades.
- Call tools only for data you don't already have."""

    def __init__(self, gateway: LLMGateway, market: MarketDataService, **kwargs: int):
        super().__init__(gateway, **kwargs)
        self._market = market

    def tools(self) -> Sequence[AgentTool]:
        return (
            AgentTool("get_quotes", "Latest quotes for up to 5 tickers.", QuotesArgs, self._quotes),
            AgentTool(
                "get_price_history",
                "Price history summary for one ticker over a range (adds a chart).",
                HistoryArgs,
                self._history,
            ),
            AgentTool(
                "get_indicators",
                "50/200-day averages, 52-week range, volatility and drawdown for a ticker.",
                SymbolArgs,
                self._indicators,
            ),
            AgentTool(
                "get_market_overview",
                "Major index levels and sector performance today.",
                NoArgs,
                self._overview,
            ),
            AgentTool("get_movers", "Biggest gainers and losers today.", MoversArgs, self._movers),
        )

    # --- Prefetch ------------------------------------------------------------

    async def prepare(self, state: FinanceState, run: AgentRun) -> Prepared:
        plan = state.get("plan")
        tickers = (plan.tickers if plan else [])[:MAX_TICKERS]
        data = await (self._ticker_data(run, tickers) if tickers else self._overview_data(run))
        return Prepared(context=as_data("market_data", to_json(data)), data=data)

    async def _ticker_data(self, run: AgentRun, tickers: list[str]) -> dict[str, Any]:
        batch = await self._market.get_quotes(tickers)
        if not batch.quotes:
            # Raises with "did you mean" suggestions when the directory knows better.
            await self._market.validate_symbol(batch.unknown[0])
            raise UnknownSymbol(batch.unknown)

        quotes = [self._record_quote(run, q) for q in batch.quotes]
        results = await asyncio.gather(
            *(self._market.get_indicators(q.value.symbol) for q in batch.quotes),
            return_exceptions=True,
        )
        indicators = []
        for result in results:
            if isinstance(result, BaseException):
                continue
            run.stamp(result.freshness)
            run.artifacts.append(
                Artifact(
                    kind="indicators",
                    title=f"{result.value.symbol} trend indicators",
                    data={
                        **result.value.model_dump(mode="json"),
                        "freshness": result.freshness.model_dump(mode="json"),
                    },
                )
            )
            indicators.append(indicator_facts(result))
        return {"quotes": quotes, "indicators": indicators, "unknown_tickers": batch.unknown}

    async def _overview_data(self, run: AgentRun) -> dict[str, Any]:
        indices, movers = await asyncio.gather(
            self._market.get_indices(), self._market.get_movers(3)
        )
        for sourced in indices:
            run.stamp(sourced.freshness)
        if indices:
            run.artifacts.append(
                Artifact(
                    kind="index_cards",
                    title="Major indices",
                    data={"indices": [i.model_dump(mode="json") for i in indices]},
                )
            )
        gainers = [quote_facts(q) for q in movers.gainers]
        losers = [quote_facts(q) for q in movers.losers]
        for q in [*movers.gainers, *movers.losers]:
            run.stamp(q.freshness)
        if gainers or losers:
            run.artifacts.append(
                Artifact(
                    kind="movers",
                    title="Today's movers",
                    data={
                        "gainers": [q.model_dump(mode="json") for q in movers.gainers],
                        "losers": [q.model_dump(mode="json") for q in movers.losers],
                    },
                )
            )
        return {
            "indices": [index_facts(i) for i in indices],
            "top_gainers": gainers,
            "top_losers": losers,
        }

    def _record_quote(self, run: AgentRun, sourced: Sourced[Quote]) -> dict[str, Any]:
        run.stamp(sourced.freshness)
        run.artifacts.append(
            Artifact(
                kind="quote_card",
                title=sourced.value.symbol,
                data={
                    "quote": sourced.value.model_dump(mode="json"),
                    "freshness": sourced.freshness.model_dump(mode="json"),
                },
            )
        )
        return quote_facts(sourced)

    # --- Tools ---------------------------------------------------------------

    async def _quotes(self, run: AgentRun, args: QuotesArgs) -> str:
        batch = await self._market.get_quotes(args.symbols)
        return to_json(
            {
                "quotes": [self._record_quote(run, q) for q in batch.quotes],
                "unknown_tickers": batch.unknown,
            }
        )

    async def _history(self, run: AgentRun, args: HistoryArgs) -> str:
        history = await self._market.get_history(args.symbol, args.range)
        bars = history.value.bars
        if not bars:
            return f"No price history for {history.value.symbol}."
        run.stamp(history.freshness)
        run.artifacts.append(
            Artifact(
                kind="price_chart",
                title=f"{history.value.symbol} ({args.range.value})",
                data={
                    "symbol": history.value.symbol,
                    "range": args.range.value,
                    "points": [{"t": b.t.isoformat(), "close": b.close} for b in bars],
                    "freshness": history.freshness.model_dump(mode="json"),
                },
            )
        )
        closes = [b.close for b in bars]
        return to_json(
            {
                "symbol": history.value.symbol,
                "range": args.range.value,
                "start": {"date": bars[0].t.date().isoformat(), "close": closes[0]},
                "end": {"date": bars[-1].t.date().isoformat(), "close": closes[-1]},
                "change_percent": percent_change(closes[0], closes[-1]),
                "high": max(b.high for b in bars),
                "low": min(b.low for b in bars),
                "bars": len(bars),
                "status": history.freshness.status.value,
            }
        )

    async def _indicators(self, run: AgentRun, args: SymbolArgs) -> str:
        sourced = await self._market.get_indicators(args.symbol)
        run.stamp(sourced.freshness)
        return to_json(indicator_facts(sourced))

    async def _overview(self, run: AgentRun, args: NoArgs) -> str:
        indices, sectors = await asyncio.gather(
            self._market.get_indices(), self._market.get_sector_performance()
        )
        for index in indices:
            run.stamp(index.freshness)
        for sector in sectors:
            run.stamp(sector.freshness)
        if sectors:
            run.artifacts.append(
                Artifact(
                    kind="sector_table",
                    title="Sector performance today",
                    data={"sectors": [s.value.model_dump(mode="json") for s in sectors]},
                )
            )
        return to_json(
            {
                "indices": [index_facts(i) for i in indices],
                "sectors": [
                    {**s.value.model_dump(mode="json"), "status": s.freshness.status.value}
                    for s in sectors
                ],
            }
        )

    async def _movers(self, run: AgentRun, args: MoversArgs) -> str:
        movers = await self._market.get_movers(args.limit)
        for q in [*movers.gainers, *movers.losers]:
            run.stamp(q.freshness)
        return to_json(
            {
                "top_gainers": [quote_facts(q) for q in movers.gainers],
                "top_losers": [quote_facts(q) for q in movers.losers],
            }
        )

    # --- Without an LLM ------------------------------------------------------

    def offline_answer(self, state: FinanceState, run: AgentRun, prepared: Prepared) -> str:
        data = prepared.data
        lines: list[str] = []
        for q in data.get("quotes", []):
            lines.append(
                f"**{q['symbol']}** is at {format_usd(q['price'])} ({_signed(q['change_percent'])} "
                f"today; {q['status']} data from {q['source']})."
            )
        for i in data.get("indicators", []):
            parts = []
            if "price_vs_sma_50_percent" in i:
                parts.append(f"{_signed(i['price_vs_sma_50_percent'])} vs its 50-day average")
            if "price_vs_sma_200_percent" in i:
                parts.append(f"{_signed(i['price_vs_sma_200_percent'])} vs its 200-day average")
            if "week52_low" in i and "week52_high" in i:
                parts.append(
                    f"52-week range {format_usd(i['week52_low'])} to {format_usd(i['week52_high'])}"
                )
            if "volatility_30d_percent" in i:
                parts.append(
                    f"30-day annualized volatility {format_percent(i['volatility_30d_percent'])}"
                )
            if parts:
                lines.append(f"- {i['symbol']}: " + "; ".join(parts) + ".")
        if data.get("indicators"):
            lines.append(
                "A price above its moving averages means it has been trending up over that "
                "window; volatility describes how widely the price has been swinging."
            )
        for idx in data.get("indices", []):
            proxy = " (via ETF proxy)" if idx["is_etf_proxy"] else ""
            lines.append(f"- **{idx['name']}**{proxy}: {_signed(idx['change_percent'])} today")
        gainers = data.get("top_gainers", [])
        losers = data.get("top_losers", [])
        if gainers:
            lines.append(
                "Top gainers: "
                + ", ".join(f"{q['symbol']} {_signed(q['change_percent'])}" for q in gainers)
            )
        if losers:
            lines.append(
                "Top losers: "
                + ", ".join(f"{q['symbol']} {_signed(q['change_percent'])}" for q in losers)
            )
        if data.get("unknown_tickers"):
            lines.append(f"I couldn't find: {', '.join(data['unknown_tickers'])}.")
        return "\n\n".join(lines) or "Market data isn't available right now."

    def confidence(self, run: AgentRun, prepared: Prepared) -> float:
        return 0.85 if run.freshness else 0.4

    def follow_ups(self, state: FinanceState, run: AgentRun, prepared: Prepared) -> list[str]:
        quotes = prepared.data.get("quotes", [])
        if quotes:
            symbol = quotes[0]["symbol"]
            return [
                "What does a 200-day moving average tell investors?",
                f"How volatile has {symbol} been compared with the S&P 500?",
                f"Show me {symbol}'s price over the last 5 years",
            ]
        return [
            "What is a market index?",
            "Why do sectors move differently on the same day?",
            "What makes a stock a top mover?",
        ]
