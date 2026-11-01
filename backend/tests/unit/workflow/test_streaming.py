"""Graph run -> chat events (CH-01, CH-03 to CH-06): what streams, and reconciliation."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.core.config import Settings
from src.core.llm import LLMGateway
from src.workflow.compliance import DISCLAIMER, FINAL_ANSWER_KEY
from src.workflow.context import StaticContextLoader
from src.workflow.graph import WorkflowDeps, build_workflow
from src.workflow.state import AgentName, AgentOutput, FinalAnswer, FinanceState, UserContext
from src.workflow.streaming import ChatEvent, _Reconciler, history, stream_turn
from tests.fakes import gateway, structured
from tests.unit.agents.test_agents import make_kb

USER = UserContext(user_id="u1")


def decision(agents: list[str], **extra: Any) -> Any:
    args: dict[str, Any] = {
        "agents": agents,
        "confidence": 0.9,
        "is_advice_request": False,
        "needs_clarification": False,
        "standalone_query": "What is a Roth IRA?",
        "tickers": [],
    }
    args.update(extra)
    return structured("RouterDecision", **args)


class TextAgent:
    """An agent that answers without an LLM, so parallel runs stay deterministic."""

    def __init__(self, name: AgentName, text: str):
        self.name, self.text = name, text

    async def run(self, state: FinanceState) -> AgentOutput:
        return AgentOutput(agent=self.name, answer_md=self.text)


def graph(gw: LLMGateway, agents: dict[AgentName, Any] | None = None) -> Any:
    if agents is None:
        from src.agents.finance_qa import FinanceQAAgent

        agents = {AgentName.FINANCE_QA: FinanceQAAgent(gw, make_kb())}
    return build_workflow(
        WorkflowDeps(
            gateway=gw,
            context_loader=StaticContextLoader(),
            agents=agents,
            config=Settings(_env_file=None).workflow,  # type: ignore[call-arg]
        ),
        InMemorySaver(),
    )


async def collect(g: Any, text: str = "What is a Roth IRA?") -> list[ChatEvent]:
    return [e async for e in stream_turn(g, thread_id="t1", user=USER, text=text, turn_id="m1")]


def shown_text(events: list[ChatEvent]) -> str:
    """Replay token/replace events the way the client does."""
    text = ""
    for event in events:
        if event.type == "token":
            text += event.text
        elif event.type == "replace":
            text = event.text
    return text


async def test_single_agent_streams_tokens_then_done() -> None:
    gw, _ = gateway(
        decision(["finance_qa"]), "A Roth IRA uses after-tax money [1].", streaming=True
    )
    events = await collect(graph(gw))
    types = [e.type for e in events]
    assert types[:2] == ["route", "agent_start"]
    assert types[-2:] == ["citation", "done"]
    tokens = [e.text for e in events if e.type == "token"]
    assert len(tokens) > 5 and tokens[0] == "A "  # word by word, not one blob
    done = events[-1]
    assert done.type == "done" and done.message.id == "m1"
    assert done.message.agents == [AgentName.FINANCE_QA]
    assert shown_text(events) == done.message.content
    assert events[-2].type == "citation" and events[-2].number == 1


async def test_several_agents_stream_only_the_merge() -> None:
    gw, _ = gateway(
        decision(["finance_qa", "market_analysis"]),
        "Merged answer about bonds and markets.",
        streaming=True,
    )
    agents = {
        AgentName.FINANCE_QA: TextAgent(AgentName.FINANCE_QA, "QA DRAFT"),
        AgentName.MARKET: TextAgent(AgentName.MARKET, "MARKET DRAFT"),
    }
    events = await collect(graph(gw, agents))
    route = events[0]
    assert route.type == "route" and route.agents == [AgentName.FINANCE_QA, AgentName.MARKET]
    assert [e.type for e in events[1:3]] == ["agent_start", "agent_start"]
    streamed = shown_text(events)
    assert "DRAFT" not in streamed and streamed.startswith("Merged answer")
    assert streamed.endswith(DISCLAIMER)  # appended by compliance as a final token
    assert not any(e.type == "replace" for e in events)


async def test_compliance_rewrite_replaces_the_streamed_draft() -> None:
    gw, _ = gateway(
        decision(["finance_qa"]),
        "You should buy index funds now [1].",
        "Index funds hold many stocks at once [1].",  # the compliance rewrite
        streaming=True,
    )
    events = await collect(graph(gw))
    replace = [e for e in events if e.type == "replace"]
    assert len(replace) == 1 and replace[0].text.startswith("Index funds hold many stocks")
    done = events[-1]
    assert done.type == "done" and "should buy" not in done.message.content
    assert shown_text(events) == done.message.content


async def test_offline_answer_arrives_as_one_token() -> None:
    events = await collect(graph(LLMGateway([])))
    tokens = [e for e in events if e.type == "token"]
    assert len(tokens) == 1
    assert shown_text(events) == events[-1].message.content  # type: ignore[union-attr]


async def test_clarification_and_redirect_have_no_agent_events() -> None:
    gw, _ = gateway(decision(["finance_qa"], confidence=0.2, clarifying_question="Which one?"))
    events = await collect(graph(gw), "that one?")
    assert events[0].type == "route" and events[0].kind == "clarification"
    assert [e.type for e in events[1:]] == ["token", "done"]

    gw, _ = gateway(decision(["market_analysis"], tickers=["NVDA"]))
    events = await collect(graph(gw), "Should I buy NVDA?")
    assert events[0].type == "route" and events[0].kind == "redirect"
    assert events[-1].type == "done" and events[-1].message.kind == "redirect"


async def test_failures_become_error_events() -> None:
    events = await collect(graph(LLMGateway([])), "   ")
    assert len(events) == 1 and events[0].type == "error"
    assert events[0].code == "validation_failed" and not events[0].retryable

    class Broken:
        def astream(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("boom")

    events = await collect(Broken())
    assert events[0].type == "error" and events[0].code == "internal_error"
    assert events[0].retryable


def test_reconciler() -> None:
    client = _Reconciler()
    client.append("Hello")
    assert client.settle("Hello") is None
    suffix = client.settle("Hello world")
    assert suffix is not None and suffix.type == "token" and suffix.text == " world"
    rewrite = client.settle("Goodbye")
    assert rewrite is not None and rewrite.type == "replace" and client.text == "Goodbye"


def test_history_rebuilds_rich_answers() -> None:
    final = FinalAnswer(answer_md="Answer [1].", agents=[AgentName.TAX], follow_ups=["Why?"])
    messages = [
        HumanMessage("Q1", id="q1"),
        AIMessage(
            "Answer [1].",
            id="a1",
            additional_kwargs={FINAL_ANSWER_KEY: final.model_dump(mode="json")},
        ),
        HumanMessage("Q2", id="q2"),
        AIMessage("", id="tool-scaffold"),
        AIMessage("Plain answer", id="a2"),
    ]
    out = history(messages)  # type: ignore[arg-type]
    assert [(m.id, m.role) for m in out] == [
        ("q1", "user"),
        ("a1", "assistant"),
        ("q2", "user"),
        ("a2", "assistant"),
    ]
    assert out[1].agents == [AgentName.TAX] and out[1].follow_ups == ["Why?"]
    assert out[3].content == "Plain answer" and out[3].agents == []
