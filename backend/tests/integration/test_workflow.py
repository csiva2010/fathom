"""The compiled LangGraph workflow end to end, with scripted LLMs and mock market data."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.core.config import Settings
from src.core.llm import LLMGateway
from src.core.services.market.factory import build_market_service
from src.core.services.market.market_data_service import MarketDataService
from src.data.db.base import Base
from src.web_app.container import AppContainer
from src.workflow.context import StaticContextLoader
from src.workflow.factory import create_workflow
from src.workflow.graph import WorkflowDeps, build_workflow, route_after_router
from src.workflow.state import AgentName, AgentOutput, FinanceState, RoutePlan, UserContext
from tests.conftest import make_settings
from tests.fakes import gateway, structured
from tests.unit.agents.test_agents import make_kb

USER = UserContext(user_id="u1")


def decision(agents: list[str], **extra: Any) -> Any:
    args: dict[str, Any] = {
        "agents": agents,
        "confidence": 0.9,
        "is_advice_request": False,
        "needs_clarification": False,
        "standalone_query": "",
        "tickers": [],
    }
    args.update(extra)
    return structured("RouterDecision", **args)


@pytest.fixture
async def market(tmp_path: Path) -> AsyncIterator[MarketDataService]:
    async with httpx.AsyncClient() as client:
        yield build_market_service(make_settings(tmp_path), client)


def workflow(gw: LLMGateway, market: MarketDataService, settings: Settings | None = None) -> Any:
    config = (settings or Settings(_env_file=None)).workflow  # type: ignore[call-arg]
    return create_workflow(config, gw, make_kb(), market, StaticContextLoader(), InMemorySaver())


async def ask(graph: Any, text: str, thread: str = "t1") -> dict[str, Any]:
    result: dict[str, Any] = await graph.ainvoke(
        {"messages": [HumanMessage(text)], "user": USER},
        {"configurable": {"thread_id": thread}},
    )
    return result


async def test_qa_turn_then_market_follow_up_keeps_memory(market: MarketDataService) -> None:
    gw, model = gateway(
        decision(["finance_qa"], standalone_query="What is a Roth IRA?"),
        "A Roth IRA uses after-tax money [1].",
        decision(["market_analysis"], tickers=["AAPL"], standalone_query="How is AAPL doing?"),
        "AAPL is above its 200-day average.",
    )
    graph = workflow(gw, market)

    first = await ask(graph, "What is a Roth IRA?")
    final = first["final"]
    assert final.agents == [AgentName.FINANCE_QA]
    assert final.citations[0].article_id == "roth-ira"
    assert final.compliance.passed
    assert [t.node for t in first["trace"]] == [
        "load_context",
        "router",
        "finance_qa",
        "synthesizer",
        "compliance",
    ]

    second = await ask(graph, "and how is AAPL doing?")
    final = second["final"]
    assert final.agents == [AgentName.MARKET]
    assert [a.kind for a in final.artifacts] == ["quote_card", "indicators"]
    assert final.freshness and final.compliance.disclaimer_added
    # Per-turn lists were reset; the conversation and focus tickers carried over.
    assert len(second["agent_outputs"]) == 1 and second["focus_tickers"] == ["AAPL"]
    assert len(second["messages"]) == 4
    router_prompt = model.calls[2][-1].text
    assert "User: What is a Roth IRA?" in router_prompt


async def test_advice_and_clarification_skip_agents(market: MarketDataService) -> None:
    gw, _ = gateway(
        decision(["market_analysis"], tickers=["NVDA"]),
        decision(["finance_qa"], confidence=0.2, clarifying_question="Which account do you mean?"),
    )
    graph = workflow(gw, market)
    advice = await ask(graph, "Should I buy NVDA?")
    assert advice["final"].kind == "redirect" and advice["agent_outputs"] == []
    clarify = await ask(graph, "that one?")
    assert clarify["final"].answer_md == "Which account do you mean?"


async def test_without_any_llm_the_graph_still_answers(market: MarketDataService) -> None:
    graph = workflow(LLMGateway([]), market)
    tax = await ask(graph, "How does a Roth IRA work?", thread="a")
    assert tax["plan"].agents == [AgentName.TAX] and tax["plan"].method == "rules"
    assert tax["final"].agents == [AgentName.FINANCE_QA]  # Q&A stands in for Tax
    assert tax["final"].citations and tax["errors"] == []

    plan = await ask(graph, "Is my portfolio on track for my house goal?", thread="b")
    notes = [e.node for e in plan["errors"]]
    assert notes == ["portfolio_analysis", "goal_planning"]
    assert "isn't available yet" in plan["final"].answer_md


class SlowAgent:
    def __init__(self, name: AgentName, delay: float, fail: bool = False):
        self.name, self.delay, self.fail = name, delay, fail
        self.started: float | None = None

    async def run(self, state: FinanceState) -> AgentOutput:
        self.started = asyncio.get_running_loop().time()
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("boom")
        return AgentOutput(agent=self.name, answer_md=f"{self.name.label} says hi")


async def test_parallel_fan_out_merges_and_survives_failures() -> None:
    qa, market = SlowAgent(AgentName.FINANCE_QA, 0.2), SlowAgent(AgentName.MARKET, 0.2)
    broken = SlowAgent(AgentName.NEWS, 0, fail=True)
    gw, _ = gateway(
        decision(["finance_qa", "market_analysis", "news_synthesizer"]),
        "Merged: both agents said hi.",
    )
    settings = Settings(_env_file=None, workflow={"agent_retries": 0})  # type: ignore[call-arg]
    graph = build_workflow(
        WorkflowDeps(
            gateway=gw,
            context_loader=StaticContextLoader(),
            agents={AgentName.FINANCE_QA: qa, AgentName.MARKET: market, AgentName.NEWS: broken},
            config=settings.workflow,
        )
    )
    result = await graph.ainvoke({"messages": [HumanMessage("compound question")], "user": USER})
    assert qa.started is not None and market.started is not None
    assert abs(qa.started - market.started) < 0.1  # ran concurrently
    final = result["final"]
    assert final.answer_md.startswith("Merged: both agents said hi.")
    assert "News Synthesizer ran into a problem" in final.answer_md
    assert set(final.agents) == {AgentName.FINANCE_QA, AgentName.MARKET}


def test_route_after_router_defaults_to_clarify() -> None:
    assert route_after_router({}, {}) == "clarify"
    sends = route_after_router({"plan": RoutePlan(agents=[AgentName.GOAL])}, {})
    assert isinstance(sends, list) and sends[0].node == "agent_unavailable"


async def test_container_builds_workflow(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        kb={
            "source_dir": str(Path(__file__).parents[1] / "fixtures" / "kb"),
            "index_dir": str(tmp_path / "index"),
            "vector_dir": str(tmp_path / "chroma"),
            "categories": ["basics", "tax"],
            "reranker": {"kind": "lexical"},
        },
    )
    container = AppContainer.build(settings)
    Base.metadata.create_all(container.engine)
    try:
        assert container.knowledge_base is not None
        assert not container.llm.available
        result = await container.workflow.ainvoke(
            {"messages": [HumanMessage("What is compound interest?")], "user": USER},
            {"configurable": {"thread_id": "c1"}},
        )
        assert result["final"].citations[0].article_id == "compound-growth"
    finally:
        await container.aclose()
