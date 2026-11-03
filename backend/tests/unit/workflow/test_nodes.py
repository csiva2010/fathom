from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session, sessionmaker

from src.core.config.settings import WorkflowConfig
from src.core.domain.risk import RiskProfile
from src.core.errors import LLMUnavailable, UnknownSymbol, ValidationFailed
from src.data.db.models import Goal, Holding, Portfolio, Profile
from src.data.db.repositories.user_repository import GoogleIdentity, UserRepository
from src.rag.models import Citation
from src.workflow.agent_runner import (
    AgentNode,
    agent_unavailable_node,
    describe_error,
    fallback_node,
)
from src.workflow.compliance import (
    DISCLAIMER,
    SCRUB_NOTE,
    UNSOURCED_NOTE,
    ComplianceNode,
    find_advice_language,
    scrub_advice,
)
from src.workflow.context import (
    DbContextLoader,
    LoadContextNode,
    StaticContextLoader,
    latest_user_text,
    recent_history,
)
from src.workflow.responses import advice_redirect_node, clarify_node
from src.workflow.router import (
    RouterNode,
    clean_tickers,
    extract_tickers,
    looks_like_advice_request,
    rule_based_decision,
)
from src.workflow.state import (
    AgentName,
    AgentOutput,
    FinalAnswer,
    FinanceState,
    Fresh,
    NodeError,
    RoutePlan,
    UserContext,
    per_turn,
)
from src.workflow.synthesizer import NOTHING_ANSWER, SynthesizerNode, renumber
from tests.fakes import gateway, structured

CONFIG = WorkflowConfig()


def cite(article: str, section: str = "S") -> Citation:
    return Citation(
        article_id=article,
        title=article,
        section=section,
        source_name="N",
        source_url="https://example.org",
    )


def decision(**overrides: Any) -> AIMessage:
    args: dict[str, Any] = {
        "agents": ["finance_qa"],
        "confidence": 0.9,
        "is_advice_request": False,
        "needs_clarification": False,
        "standalone_query": "q",
        "tickers": [],
    }
    args.update(overrides)
    return structured("RouterDecision", **args)


def turn(text: str, **extra: Any) -> FinanceState:
    return {"messages": [HumanMessage(text)], "user": UserContext(user_id="u1"), **extra}  # type: ignore[typeddict-item]


# --- State helpers ------------------------------------------------------------


def test_per_turn_reducer_appends_and_resets() -> None:
    assert per_turn([1], [2]) == [1, 2]
    assert per_turn([1], Fresh([3])) == [3]
    assert per_turn(None, [4]) == [4]


def test_message_helpers() -> None:
    state: FinanceState = {
        "messages": [
            HumanMessage("first"),
            AIMessage("", tool_calls=[{"name": "x", "args": {}, "id": "1"}]),
            AIMessage("answer"),
            HumanMessage("second"),
        ]
    }
    assert latest_user_text(state) == "second"
    assert [m.text for m in recent_history(state, 5)] == ["first", "answer"]
    assert recent_history(state, 0) == []
    assert latest_user_text({"messages": []}) == ""


# --- Router -------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Should I buy NVDA?",
        "is TSLA a good buy right now",
        "what stocks should I pick",
        "buy or hold AAPL?",
        "Is it worth buying bitcoin",
        "where should i invest my bonus",
    ],
)
def test_advice_detector_flags(text: str) -> None:
    assert looks_like_advice_request(text)


@pytest.mark.parametrize("text", ["What is a stock buyback?", "How do people decide when to sell?"])
def test_advice_detector_ignores_education(text: str) -> None:
    assert not looks_like_advice_request(text)


def test_ticker_extraction() -> None:
    assert extract_tickers("Compare AAPL and $SPY with my IRA and ETF") == ["AAPL", "SPY"]
    assert extract_tickers("Is BRK.B in the S&P 500?") == ["BRK.B"]
    assert clean_tickers(["$aapl", "AAPL", "not a ticker", "msft"], 3) == ["AAPL", "MSFT"]


def test_rule_based_routing() -> None:
    assert rule_based_decision("What is AAPL trading at?", []).agents == [AgentName.MARKET]
    assert rule_based_decision("How much tax on capital gains?", []).agents == [AgentName.TAX]
    multi = rule_based_decision("Is my portfolio on track for my house goal?", [])
    assert multi.agents == [AgentName.PORTFOLIO, AgentName.GOAL]
    assert rule_based_decision("What is diversification?", []).agents == [AgentName.FINANCE_QA]
    follow_up = rule_based_decision("what about its 52-week range?", ["AAPL"])
    assert follow_up.tickers == ["AAPL"] and follow_up.agents == [AgentName.MARKET]
    assert rule_based_decision("NVDA", []).agents == [AgentName.MARKET]
    assert rule_based_decision("hmm", []).confidence < 0.6
    # "index fund" is a concept, not the market's indices (found by the routing eval).
    assert rule_based_decision("What is an index fund?", []).agents == [AgentName.FINANCE_QA]
    mixed = rule_based_decision("What's an ETF, and how is SPY doing today?", [])
    assert mixed.agents == [AgentName.MARKET, AgentName.FINANCE_QA]


async def test_router_llm_plan_and_focus_tickers() -> None:
    gw, model = gateway(
        decision(
            agents=["market_analysis", "market_analysis", "finance_qa"],
            tickers=["$aapl"],
            standalone_query="What is Apple's P/E?",
        )
    )
    state = turn("what's its P/E?", focus_tickers=["AAPL"], portfolio=None, goals=[])
    state["messages"] = [HumanMessage("How is AAPL?"), AIMessage("It is up."), *state["messages"]]
    update = await RouterNode(gw, CONFIG)(state)
    plan: RoutePlan = update["plan"]
    assert plan.agents == [AgentName.MARKET, AgentName.FINANCE_QA]
    assert plan.tickers == ["AAPL"] and update["focus_tickers"] == ["AAPL"]
    assert plan.method == "llm" and not plan.needs_clarification
    assert "User: How is AAPL?" in model.calls[0][-1].text


async def test_router_low_confidence_asks_and_advice_overrides() -> None:
    gw, _ = gateway(decision(confidence=0.3), decision(confidence=0.3, agents=[]))
    clarify = (await RouterNode(gw, CONFIG)(turn("hmm")))["plan"]
    assert clarify.needs_clarification and clarify.clarifying_question
    advice = (await RouterNode(gw, CONFIG)(turn("Should I sell my MSFT?")))["plan"]
    assert advice.is_advice_request and not advice.needs_clarification
    assert advice.agents == [AgentName.FINANCE_QA]


async def test_router_falls_back_to_rules_without_llm() -> None:
    gw, _ = gateway(RuntimeError("down"))
    update = await RouterNode(gw, CONFIG)(turn("What is AAPL trading at?", focus_tickers=["MSFT"]))
    assert update["plan"].method == "rules"
    assert update["focus_tickers"] == ["AAPL"]


# --- Context ------------------------------------------------------------------


async def test_load_context_validates_and_resets() -> None:
    node = LoadContextNode(StaticContextLoader(), max_message_chars=100)
    update = await node(turn("hello"))
    assert update["agent_outputs"] == [] and isinstance(update["agent_outputs"], Fresh)
    assert update["trace"][0].node == "load_context"
    with pytest.raises(ValidationFailed):
        await node(turn("x" * 101))
    with pytest.raises(ValidationFailed):
        await node(turn("   "))
    with pytest.raises(ValidationFailed):
        await node({"messages": [HumanMessage("hi")]})


async def test_db_context_loader_scopes_by_user(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as db:
        users = UserRepository(db)
        me = users.upsert_from_google(GoogleIdentity("g1", "a@example.com", "A", None))
        other = users.upsert_from_google(GoogleIdentity("g2", "b@example.com", "B", None))
        profile = db.get(Profile, me.id)
        assert profile is not None
        profile.experience_level, profile.risk_profile = "advanced", "aggressive"
        db.add(
            Portfolio(
                user_id=me.id,
                name="Mine",
                holdings=[Holding(symbol="VTI", quantity=3, asset_class="etf")],
            )
        )
        db.add(Portfolio(user_id=other.id, name="Theirs", holdings=[]))
        db.add(
            Goal(
                user_id=me.id,
                type="house",
                target_amount=50000,
                target_date=date(2030, 1, 1),
                risk_profile="moderate",
            )
        )
        db.commit()
        my_id, other_id = me.id, other.id

    loaded = await DbContextLoader(session_factory).load(UserContext(user_id=my_id))
    assert loaded.user.experience_level == "advanced"
    assert loaded.user.risk_profile is RiskProfile.AGGRESSIVE
    assert loaded.portfolio is not None and loaded.portfolio.name == "Mine"
    assert loaded.portfolio.holdings[0].symbol == "VTI"
    assert [g.type for g in loaded.goals] == ["house"]

    theirs = await DbContextLoader(session_factory).load(UserContext(user_id=other_id))
    assert theirs.portfolio is not None and theirs.portfolio.name == "Theirs" and theirs.goals == []
    assert theirs.user.experience_level == "beginner"


# --- Agent runner and fallback ------------------------------------------------


class StubAgent:
    name = AgentName.MARKET

    def __init__(self, *outcomes: Any):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def run(self, state: FinanceState) -> AgentOutput:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome == "slow":
            await asyncio.sleep(1)
        return AgentOutput(agent=self.name, answer_md="ok")


async def test_agent_node_retries_then_succeeds() -> None:
    agent = StubAgent(LLMUnavailable("busy"), "fine")
    update = await AgentNode(agent, timeout_seconds=1, retries=1)({})
    assert update["agent_outputs"][0].answer_md == "ok" and agent.calls == 2
    assert update["trace"][0].detail["attempts"] == 2


async def test_agent_node_records_errors() -> None:
    unknown = await AgentNode(StubAgent(UnknownSymbol(["ZZZ"])), timeout_seconds=1, retries=1)({})
    assert unknown["errors"][0].code == "unknown_symbol"  # not retried
    slow = await AgentNode(StubAgent("slow", "slow"), timeout_seconds=0.01, retries=1)({})
    assert slow["errors"][0].code == "timeout"
    crash = await AgentNode(StubAgent(KeyError("x"), KeyError("y")), timeout_seconds=1, retries=1)(
        {}
    )
    assert crash["errors"][0].code == "agent_error"


async def test_fallback_notes() -> None:
    unavailable = await agent_unavailable_node({"agent": "goal_planning"})
    errors = [
        *unavailable["errors"],
        NodeError(node="market_analysis", code="timeout", message="slow"),
        NodeError(node="market_analysis", code="unknown_symbol", message="We couldn't find ZZZ."),
        NodeError(node="mystery", code="agent_error", message="x"),
    ]
    notes = fallback_node({"errors": errors})["notes"]
    assert notes[0] == "Goal Planning isn't available yet, so this answer doesn't cover that part."
    assert "took too long" in notes[1] and notes[2] == "We couldn't find ZZZ."
    assert describe_error(errors[3]).startswith("mystery ran into a problem")
    assert fallback_node({"errors": []}) == {}


# --- Synthesizer --------------------------------------------------------------


def output(agent: AgentName, text: str, citations: list[Citation] | None = None) -> AgentOutput:
    return AgentOutput(
        agent=agent, answer_md=text, citations=citations or [], follow_ups=[f"{agent.value}?"]
    )


def test_renumber_shares_citations() -> None:
    texts, merged = renumber(
        [
            output(AgentName.FINANCE_QA, "A [1] B [2]", [cite("a"), cite("b")]),
            output(AgentName.TAX, "C [1] D [2] E [9]", [cite("b"), cite("c")]),
        ]
    )
    assert texts == ["A [1] B [2]", "C [2] D [3] E [9]"]
    assert [c.article_id for c in merged] == ["a", "b", "c"]


async def test_synthesizer_passthrough_merge_and_empty() -> None:
    gw, model = gateway("Merged answer [1][2].", RuntimeError("down"))
    node = SynthesizerNode(gw)
    plan = RoutePlan(agents=[AgentName.MARKET, AgentName.FINANCE_QA], standalone_query="q")
    outputs = [output(AgentName.FINANCE_QA, "qa [1]", [cite("a")]), output(AgentName.MARKET, "mkt")]

    single = (await node({"agent_outputs": outputs[:1], "plan": plan, "notes": ["heads up"]}))[
        "draft"
    ]
    assert single.answer_md.startswith("qa [1]") and "> **Note:** heads up" in single.answer_md

    merged = (await node({"agent_outputs": outputs, "plan": plan}))["draft"]
    assert merged.answer_md == "Merged answer [1][2]."
    assert merged.agents == [AgentName.MARKET, AgentName.FINANCE_QA]  # plan order
    assert '<data agent="Market Analysis">' in model.calls[0][-1].text

    joined = (await node({"agent_outputs": outputs, "plan": plan}))["draft"]
    assert "### Market Analysis" in joined.answer_md and "### Finance Q&A" in joined.answer_md

    empty = (await node({"agent_outputs": []}))["draft"]
    assert empty.answer_md == NOTHING_ANSWER


# --- Compliance ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "You should buy NVDA now.",
        "I recommend selling your bonds.",
        "This is a strong buy.",
        "Guaranteed returns of 12%!",
        "It's a good time to buy.",
        "Buy it now before it's too late",
    ],
)
def test_advice_language_detected(text: str) -> None:
    assert find_advice_language(text)


def test_scrub_removes_only_offending_sentences() -> None:
    assert scrub_advice("Bonds pay interest. You should buy bonds. Rates vary.") == (
        "Bonds pay interest. Rates vary."
    )


async def test_compliance_rewrites_advice_once() -> None:
    gw, model = gateway("Some investors consider bonds for stability.")
    draft = FinalAnswer(answer_md="You should buy bonds.", agents=[AgentName.FINANCE_QA])
    update = await ComplianceNode(gw)({"draft": draft})
    final = update["final"]
    assert final.answer_md.startswith("Some investors consider bonds")
    assert final.compliance.rewritten and final.compliance.issues == ["advice_language"]
    assert DISCLAIMER in final.answer_md  # "bonds" is advice-adjacent
    assert update["messages"][0].text == final.answer_md
    assert len(model.calls) == 1


async def test_compliance_scrubs_when_rewrite_fails() -> None:
    for replies in (("You should buy NVDA anyway.",), (RuntimeError("down"),)):
        gw, _ = gateway(*replies)
        draft = FinalAnswer(answer_md="NVDA rose 3% today. You should buy NVDA.")
        final = (await ComplianceNode(gw)({"draft": draft}))["final"]
        assert "You should buy" not in final.answer_md
        assert SCRUB_NOTE in final.answer_md and "NVDA rose 3% today." in final.answer_md


async def test_compliance_flags_unsourced_kb_answer_and_skips_clarifications() -> None:
    gw, _ = gateway()
    unsourced = AgentOutput(agent=AgentName.FINANCE_QA, answer_md="x", confidence=0.8)
    final = (
        await ComplianceNode(gw)(
            {"draft": FinalAnswer(answer_md="Rates explained."), "agent_outputs": [unsourced]}
        )
    )["final"]
    assert UNSOURCED_NOTE in final.answer_md and not final.compliance.passed

    clarification = FinalAnswer(kind="clarification", answer_md="Which stock do you mean?")
    final = (await ComplianceNode(gw)({"draft": clarification}))["final"]
    assert final.answer_md == "Which stock do you mean?" and final.compliance.passed

    plain = (await ComplianceNode(gw)({}))["final"]
    assert plain.compliance.passed and not plain.compliance.disclaimer_added


# --- Fixed responses ----------------------------------------------------------


def test_advice_redirect_and_clarify() -> None:
    redirect = advice_redirect_node({"plan": RoutePlan(tickers=["NVDA"], is_advice_request=True)})
    draft = redirect["draft"]
    assert draft.kind == "redirect" and "buy, sell or hold NVDA" in draft.answer_md
    assert draft.follow_ups[0] == "Show me NVDA's price trend and volatility"
    assert not find_advice_language(draft.answer_md)
    generic = advice_redirect_node({})["draft"]
    assert "a specific investment" in generic.answer_md

    asked = clarify_node(
        {"plan": RoutePlan(needs_clarification=True, clarifying_question="Which?")}
    )
    assert asked["draft"].answer_md == "Which?"
    assert clarify_node({})["draft"].kind == "clarification"
