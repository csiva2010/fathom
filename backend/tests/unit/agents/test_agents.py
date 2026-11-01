from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents.base_agent import AgentRun, as_data
from src.agents.finance_qa import KB_UNAVAILABLE_ANSWER, NO_CONTEXT_ANSWER, FinanceQAAgent
from src.agents.market_analysis import MarketAnalysisAgent
from src.core.config.settings import RetrievalConfig
from src.core.errors import UnknownSymbol
from src.core.services.market.factory import build_market_service
from src.core.services.market.market_data_service import MarketDataService
from src.rag.glossary import Glossary
from src.rag.keyword.bm25_index import BM25Index
from src.rag.knowledge_base import KnowledgeBase
from src.rag.models import Citation, GlossaryTerm
from src.rag.reranker import LexicalReranker
from src.rag.retriever import HybridRetriever
from src.workflow.state import AgentName, FinanceState, RoutePlan, UserContext
from tests.conftest import make_settings
from tests.fakes import gateway, tool_call
from tests.unit.rag.test_retrieval import CHUNKS


def make_kb() -> KnowledgeBase:
    return KnowledgeBase(
        retriever=HybridRetriever(BM25Index(CHUNKS), LexicalReranker(0.5), RetrievalConfig()),
        glossary=Glossary(
            [
                GlossaryTerm(
                    term="Roth IRA",
                    definition="An IRA funded with after-tax money.",
                    related=["Traditional IRA"],
                ),
                GlossaryTerm(term="Quasar", definition="A made-up term used only in tests."),
            ]
        ),
    )


def state(
    question: str, *, tickers: list[str] | None = None, level: str = "beginner"
) -> FinanceState:
    return {
        "messages": [
            HumanMessage("earlier question"),
            AIMessage("earlier answer"),
            HumanMessage(question),
        ],
        "user": UserContext(user_id="u1", experience_level=level),  # type: ignore[arg-type]
        "plan": RoutePlan(agents=[], standalone_query=question, tickers=tickers or []),
    }


@pytest.fixture
async def market(tmp_path: Path) -> AsyncIterator[MarketDataService]:
    async with httpx.AsyncClient() as client:
        yield build_market_service(make_settings(tmp_path), client)


# --- Finance Q&A ---------------------------------------------------------------


async def test_qa_answers_from_sources_with_citations() -> None:
    gw, model = gateway("A **Roth IRA** uses after-tax money [1].")
    output = await FinanceQAAgent(gw, make_kb()).run(state("What is a Roth IRA?", level="advanced"))
    assert output.agent is AgentName.FINANCE_QA
    assert output.answer_md.endswith("[1].")
    assert output.grounded and output.citations[0].article_id == "roth-ira"
    assert output.follow_ups[0] == "What is Traditional IRA?"
    prompt = model.calls[0]
    assert "experienced" in prompt[0].text  # level guide in the system prompt
    assert [m.text for m in prompt[1:3]] == ["earlier question", "earlier answer"]
    assert '<data source="knowledge_base">' in prompt[-1].text
    assert '<data source="glossary">' in prompt[-1].text


async def test_qa_says_it_does_not_know_without_calling_llm() -> None:
    gw, model = gateway()
    output = await FinanceQAAgent(gw, make_kb()).run(state("explain quantum chromodynamics"))
    assert output.answer_md == NO_CONTEXT_ANSWER
    assert not output.grounded and output.confidence < 0.5
    assert model.calls == []


async def test_qa_without_kb() -> None:
    gw, _ = gateway()
    output = await FinanceQAAgent(gw, None).run(state("What is a bond?"))
    assert output.answer_md == KB_UNAVAILABLE_ANSWER


async def test_qa_glossary_only_answer() -> None:
    gw, _ = gateway("A quasar is a test term.")
    output = await FinanceQAAgent(gw, make_kb()).run(state("What is a quasar?"))
    assert output.confidence == 0.5 and output.citations == []


async def test_qa_tools_search_and_define() -> None:
    gw, model = gateway(
        tool_call("search_kb", {"query": "bond interest"}, "c1"),
        AIMessage(
            "",
            tool_calls=[
                {"name": "define_term", "args": {"term": "Roth IRA"}, "id": "c2"},
                {"name": "define_term", "args": {"term": "Roth IRAA"}, "id": "c3"},
                {"name": "search_kb", "args": {"query": "zzz qqq"}, "id": "c4"},
            ],
        ),
        "Bonds pay interest [2].",
    )
    output = await FinanceQAAgent(gw, make_kb()).run(state("What is a Roth IRA?"))
    tool_results = [m.text for m in model.calls[-1] if isinstance(m, ToolMessage)]
    assert "[2] Bonds > Overview" in tool_results[0]
    assert tool_results[1].startswith("Roth IRA: An IRA")
    assert "Close matches: Roth IRA" in tool_results[2]
    assert tool_results[3].startswith("NO_CONTEXT")
    assert [c.article_id for c in output.citations] == ["roth-ira", "bonds"]


async def test_qa_offline_answer_quotes_sources() -> None:
    gw, _ = gateway(RuntimeError("llm down"))
    output = await FinanceQAAgent(gw, make_kb()).run(state("What is a Roth IRA?"))
    assert output.answer_md.startswith("**Roth IRA**: An IRA funded")
    assert "Here's what my sources say" in output.answer_md
    assert output.grounded


async def test_empty_llm_reply_uses_offline_answer() -> None:
    gw, _ = gateway("   ")
    output = await FinanceQAAgent(gw, make_kb()).run(state("What is a Roth IRA?"))
    assert "Here's what my sources say" in output.answer_md


# --- Base agent tool loop -------------------------------------------------------


async def test_tool_loop_refuses_unknown_tools_and_bad_args() -> None:
    gw, model = gateway(
        AIMessage(
            "",
            tool_calls=[
                {"name": "place_order", "args": {"symbol": "NVDA"}, "id": "c1"},
                {"name": "define_term", "args": {}, "id": "c2"},
            ],
        ),
        tool_call("search_kb", {"query": "roth"}, "c3"),
        "final",
    )
    agent = FinanceQAAgent(gw, make_kb(), max_tool_rounds=2)
    output = await agent.run(state("What is a Roth IRA?"))
    results = [m.text for m in model.calls[1] if isinstance(m, ToolMessage)]
    assert results[0] == "Error: tool 'place_order' is not available to this agent."
    assert results[1].startswith("Error: invalid arguments")
    # Two rounds offer tools; the last call must answer without them.
    assert len(model.calls) == 3 and len(model.bound_tools) == 2
    assert output.answer_md == "final"


async def test_tool_errors_are_reported_to_the_model(market: MarketDataService) -> None:
    gw, model = gateway(tool_call("get_indicators", {"symbol": "ZZZZQ"}), "done")
    agent = MarketAnalysisAgent(gw, market)

    async def boom(run: AgentRun, args: Any) -> str:
        raise RuntimeError("kaput")

    output = await agent.run(state("How is AAPL doing?", tickers=["AAPL"]))
    error = next(m.text for m in model.calls[1] if isinstance(m, ToolMessage))
    assert error.startswith("Error:")
    assert output.answer_md == "done"

    tools = {t.name: t for t in agent.tools()}
    run = AgentRun()
    failing = type(tools["get_movers"])("get_movers", "x", tools["get_movers"].args_schema, boom)
    result = await agent._execute(
        {"name": "get_movers", "args": {}, "id": "1"}, {"get_movers": failing}, run
    )
    assert result.startswith("Error: the tool failed")


def test_agent_run_dedupes_citations_and_freshness() -> None:
    run = AgentRun()
    citation = Citation(
        article_id="a", title="A", section="S", source_name="N", source_url="https://x.org"
    )
    assert run.cite(citation) == 1 and run.cite(citation) == 1
    assert as_data("x", "y") == '<data source="x">\ny\n</data>'


# --- Market analysis -------------------------------------------------------------


async def test_market_prefetches_quotes_and_indicators(market: MarketDataService) -> None:
    gw, model = gateway("AAPL is trading above its averages.")
    output = await MarketAnalysisAgent(gw, market).run(
        state("How is AAPL doing?", tickers=["AAPL"])
    )
    assert output.agent is AgentName.MARKET
    assert [a.kind for a in output.artifacts] == ["quote_card", "indicators"]
    assert output.freshness and output.freshness[0].status.value == "mock"
    assert '"symbol":"AAPL"' in model.calls[0][-1].text
    assert output.confidence == 0.85
    assert "AAPL" in output.follow_ups[1]


async def test_market_overview_without_tickers(market: MarketDataService) -> None:
    gw, _ = gateway(RuntimeError("llm down"))
    output = await MarketAnalysisAgent(gw, market).run(state("How is the market today?"))
    kinds = [a.kind for a in output.artifacts]
    assert "index_cards" in kinds and "movers" in kinds
    assert "S&P 500" in output.answer_md and "Top gainers" in output.answer_md
    assert output.follow_ups[0] == "What is a market index?"


async def test_market_offline_answer_for_tickers(market: MarketDataService) -> None:
    gw, _ = gateway(RuntimeError("llm down"))
    output = await MarketAnalysisAgent(gw, market).run(
        state("AAPL and ZZZZQ?", tickers=["AAPL", "ZZZZQ"])
    )
    assert "**AAPL** is at $" in output.answer_md
    assert "50-day average" in output.answer_md
    assert "I couldn't find: ZZZZQ." in output.answer_md


async def test_market_unknown_ticker_raises(market: MarketDataService) -> None:
    gw, _ = gateway()
    with pytest.raises(UnknownSymbol):
        await MarketAnalysisAgent(gw, market).run(state("How is ZZZZQ?", tickers=["ZZZZQ"]))


async def test_market_tools(market: MarketDataService) -> None:
    gw, model = gateway(
        AIMessage(
            "",
            tool_calls=[
                {"name": "get_quotes", "args": {"symbols": ["MSFT"]}, "id": "1"},
                {"name": "get_price_history", "args": {"symbol": "MSFT", "range": "1M"}, "id": "2"},
                {"name": "get_indicators", "args": {"symbol": "MSFT"}, "id": "3"},
                {"name": "get_market_overview", "args": {}, "id": "4"},
                {"name": "get_movers", "args": {"limit": 2}, "id": "5"},
            ],
        ),
        "Here is the picture.",
    )
    output = await MarketAnalysisAgent(gw, market).run(state("Tell me about the market"))
    results = [m.text for m in model.calls[1] if isinstance(m, ToolMessage)]
    assert '"symbol":"MSFT"' in results[0]
    assert '"range":"1M"' in results[1] and '"change_percent"' in results[1]
    assert '"sma_50"' in results[2]
    assert '"sectors"' in results[3]
    assert '"top_gainers"' in results[4]
    kinds = {a.kind for a in output.artifacts}
    assert {"price_chart", "sector_table", "quote_card"} <= kinds
