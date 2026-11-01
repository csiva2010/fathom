"""News Synthesizer agent (AG-05, MD-10): recent news for a ticker or the market, explained.

Headlines come from `MarketDataService.get_news`, which falls back to an empty list, never
to invented stories; with no news the agent says so without an LLM call. Headlines and
summaries are third-party text, so they enter the prompt wrapped as data (NF-S02). The
LLM can pull KB context with `search_kb` to explain why a story matters, citing it as [n].
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from src.agents.base_agent import AgentRun, AgentTool, BaseAgent, Prepared, as_data, to_json
from src.core.domain.market import NewsItem
from src.core.llm import LLMGateway
from src.core.services.market.market_data_service import MarketDataService
from src.rag.knowledge_base import KnowledgeBase
from src.workflow.state import AgentName, AgentOutput, Artifact, FinanceState

NEWS_LIMIT = 6
MAX_SYMBOLS = 5
SUMMARY_CHARS = 400

_ABOUT_PORTFOLIO = re.compile(r"\bmy (portfolio|holdings|positions|stocks|investments)\b", re.I)


class NewsArgs(BaseModel):
    symbols: list[str] = Field(
        default_factory=list, max_length=MAX_SYMBOLS, description="Tickers; empty = market news"
    )
    limit: int = Field(default=NEWS_LIMIT, ge=1, le=10)


class SearchKbArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300, description="Concept to look up")


def news_facts(items: Sequence[NewsItem]) -> list[dict[str, Any]]:
    return [
        {
            "headline": n.headline,
            "source": n.source,
            "published": n.published_at.date().isoformat(),
            "symbols": n.symbols,
            "summary": n.summary[:SUMMARY_CHARS],
        }
        for n in items
    ]


class NewsSynthesizerAgent(BaseAgent):
    name = AgentName.NEWS
    role_prompt = """You are the News Synthesizer agent. You summarize recent news and \
explain why it could matter to investors.
- Use only the stories in the news data. Refer to a story by its source and date (for \
example "Reuters, Oct 30"); do not use [n] markers for news.
- Group related stories, say what happened, then explain the concept behind why it can \
move prices (earnings expectations, interest rates, guidance) in plain language.
- Never predict where a price will go and never suggest trading on the news.
- Use search_kb to explain a concept; cite those excerpts inline as [1], [2]."""

    def __init__(
        self,
        gateway: LLMGateway,
        market: MarketDataService,
        knowledge_base: KnowledgeBase | None,
        **kwargs: int,
    ):
        super().__init__(gateway, **kwargs)
        self._market = market
        self._kb = knowledge_base

    def tools(self) -> Sequence[AgentTool]:
        tools = [
            AgentTool(
                "get_news",
                "Recent news for up to 5 tickers, or market news when none are given.",
                NewsArgs,
                self._news_tool,
            )
        ]
        if self._kb is not None:
            tools.append(
                AgentTool(
                    "search_kb",
                    "Search the finance knowledge base. Returns numbered excerpts to cite as [n].",
                    SearchKbArgs,
                    self._search_tool,
                )
            )
        return tools

    # --- Prefetch ------------------------------------------------------------

    def symbols(self, state: FinanceState) -> list[str]:
        plan = state.get("plan")
        if plan and plan.tickers:
            return plan.tickers[:MAX_SYMBOLS]
        portfolio = state.get("portfolio")
        if portfolio and _ABOUT_PORTFOLIO.search(self.question(state)):
            return list(dict.fromkeys(h.symbol for h in portfolio.holdings))[:MAX_SYMBOLS]
        return []

    async def prepare(self, state: FinanceState, run: AgentRun) -> Prepared:
        symbols = self.symbols(state)
        news = await self._market.get_news(symbols or None, NEWS_LIMIT)
        subject = ", ".join(symbols) if symbols else "the market"
        if not news.value:
            return Prepared(early=self._no_news(subject))
        self._record(run, news.value, subject, news.freshness.model_dump(mode="json"))
        run.stamp(news.freshness)
        context = {"subject": subject, "stories": news_facts(news.value)}
        return Prepared(
            context=as_data("news", to_json(context)),
            data={"items": news.value, "subject": subject},
        )

    def _no_news(self, subject: str) -> AgentOutput:
        return AgentOutput(
            agent=self.name,
            answer_md=(
                f"I couldn't find any recent news for {subject}. The news feed may be "
                "unavailable right now, and I won't make up headlines."
            ),
            confidence=0.3,
            follow_ups=[
                "How do earnings reports move stock prices?",
                "How is the market doing today?",
            ],
        )

    def _record(
        self, run: AgentRun, items: Sequence[NewsItem], subject: str, freshness: dict[str, Any]
    ) -> None:
        run.artifacts.append(
            Artifact(
                kind="news_list",
                title=f"Recent news: {subject}",
                data={
                    "items": [n.model_dump(mode="json") for n in items],
                    "freshness": freshness,
                },
            )
        )

    # --- Tools ---------------------------------------------------------------

    async def _news_tool(self, run: AgentRun, args: NewsArgs) -> str:
        news = await self._market.get_news(args.symbols or None, args.limit)
        if not news.value:
            return "No recent news found."
        run.stamp(news.freshness)
        subject = ", ".join(args.symbols) if args.symbols else "the market"
        self._record(run, news.value, subject, news.freshness.model_dump(mode="json"))
        return as_data("news", to_json(news_facts(news.value)))

    async def _search_tool(self, run: AgentRun, args: SearchKbArgs) -> str:
        assert self._kb is not None
        result = await self._kb.retriever.search(args.query)
        if not result.found:
            return "NO_CONTEXT: nothing in the knowledge base matches that query."
        lines = []
        for hit, citation in zip(result.chunks, result.citations_per_chunk(), strict=True):
            lines.append(
                f"[{run.cite(citation)}] {hit.chunk.title} > {hit.chunk.section}\n{hit.chunk.text}"
            )
        return as_data("knowledge_base", "\n\n".join(lines))

    # --- Without an LLM ------------------------------------------------------

    def offline_answer(self, state: FinanceState, run: AgentRun, prepared: Prepared) -> str:
        items: list[NewsItem] = prepared.data["items"]
        lines = [f"Here are the latest headlines for {prepared.data['subject']}:"]
        for n in items:
            source = f"{n.source}, " if n.source else ""
            lines.append(f"- **{n.headline}** ({source}{n.published_at:%b %d})")
        lines.append(
            "A single story rarely explains a price move on its own; markets react to how news "
            "compares with what investors already expected."
        )
        return "\n".join(lines[:-1]) + "\n\n" + lines[-1]

    def confidence(self, run: AgentRun, prepared: Prepared) -> float:
        return 0.75

    def follow_ups(self, state: FinanceState, run: AgentRun, prepared: Prepared) -> list[str]:
        return [
            "Why do stocks move on earnings news?",
            "How do interest rates affect stock prices?",
            "How is the market doing today?",
        ]
