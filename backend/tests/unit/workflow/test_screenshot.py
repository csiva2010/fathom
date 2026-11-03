"""Reading holdings from a chat screenshot and routing it (CH-09)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from src.core.config.settings import WorkflowConfig
from src.core.llm import LLMGateway
from src.workflow.router import RouterNode, screenshot_this_turn, with_portfolio_agent
from src.workflow.screenshot import (
    EXTRACT_PROMPT,
    SCREENSHOT_KEY,
    ExtractedHolding,
    ReadScreenshotNode,
    ScreenshotInput,
    clean_holdings,
)
from src.workflow.state import (
    AgentName,
    FinanceState,
    RoutePlan,
    ScreenshotHolding,
    ScreenshotRead,
    UserContext,
)
from tests.fakes import gateway, structured

IMAGE = ScreenshotInput(media_type="image/png", data=b"\x89PNG\r\n\x1a\nfake")


def config(image: Any = IMAGE) -> dict[str, Any]:
    return {"configurable": {"thread_id": "t1", SCREENSHOT_KEY: image}}


def turn(text: str = "Analyze the portfolio in this screenshot.", **extra: Any) -> FinanceState:
    state: dict[str, Any] = {
        "messages": [HumanMessage(text)],
        "user": UserContext(user_id="u1"),
        "turn_id": "turn-1",
    }
    state.update(extra)
    return state  # type: ignore[return-value]


def extracted(**args: Any) -> Any:
    return structured("ExtractedHoldings", **args)


def row(symbol: str, quantity: float, price: float | None = None, **extra: Any) -> ExtractedHolding:
    return ExtractedHolding(symbol=symbol, quantity=quantity, price=price, **extra)


def test_clean_holdings_normalises_merges_and_caps() -> None:
    rows = clean_holdings(
        [
            row("$aapl", 10, 190.5, name="Apple Inc."),
            row("AAPL", 5),  # same symbol in another account: quantities add up
            row("vti", 3, -1),  # a nonsense price is dropped, the row kept
            row("NOT A TICKER", 4),
            row("BND", 0),
            row("MSFT", 2),
            row("GOOG", 1),
        ],
        limit=3,
    )
    assert [(r.symbol, r.quantity, r.price) for r in rows] == [
        ("AAPL", 15, 190.5),
        ("VTI", 3, None),
        ("MSFT", 2, None),
    ]
    assert rows[0].name == "Apple Inc."


async def test_without_an_image_the_node_does_nothing() -> None:
    gw, model = gateway()
    node = ReadScreenshotNode(gw, max_holdings=25)
    assert await node(turn(), {"configurable": {"thread_id": "t1"}}) == {}
    assert await node(turn(), config(image="a string is not an image")) == {}
    assert model.calls == []


async def test_reads_holdings_from_the_image() -> None:
    gw, model = gateway(
        extracted(
            is_portfolio=True,
            holdings=[{"symbol": "VTI", "quantity": 12, "price": 280.1, "name": "Vanguard"}],
        )
    )
    update = await ReadScreenshotNode(gw, max_holdings=25)(turn(), config())
    read: ScreenshotRead = update["screenshot"]
    assert read.status == "read" and read.turn_id == "turn-1"
    assert read.holdings == [
        ScreenshotHolding(symbol="VTI", quantity=12, price=280.1, name="Vanguard")
    ]
    assert update["trace"][0].node == "read_screenshot"

    system, human = model.calls[0]
    assert system.text == EXTRACT_PROMPT
    image_block = next(b for b in human.content if b["type"] == "image")
    assert image_block["mime_type"] == "image/png" and image_block["base64"]


async def test_image_without_holdings_or_without_a_model() -> None:
    gw, _ = gateway(extracted(is_portfolio=False, holdings=[{"symbol": "AAPL", "quantity": 1}]))
    empty = await ReadScreenshotNode(gw, max_holdings=25)(turn(), config())
    assert empty["screenshot"].status == "empty" and not empty["screenshot"].holdings

    offline = await ReadScreenshotNode(LLMGateway([]), max_holdings=25)(turn(), config())
    assert offline["screenshot"].status == "unavailable"


def test_screenshot_routing_helpers() -> None:
    shot = ScreenshotRead(turn_id="turn-1", status="read")
    assert screenshot_this_turn(turn(screenshot=shot))
    assert not screenshot_this_turn(turn(screenshot=shot.model_copy(update={"turn_id": "old"})))
    assert not screenshot_this_turn(turn())

    plan = RoutePlan(
        agents=[AgentName.MARKET, AgentName.PORTFOLIO, AgentName.NEWS],
        needs_clarification=True,
        clarifying_question="What do you mean?",
    )
    forced = with_portfolio_agent(plan, max_agents=2)
    assert forced.agents == [AgentName.PORTFOLIO, AgentName.MARKET]
    assert not forced.needs_clarification and forced.clarifying_question is None


async def test_router_sends_a_screenshot_turn_to_the_portfolio_agent() -> None:
    gw, model = gateway(
        structured(
            "RouterDecision",
            agents=["finance_qa"],
            confidence=0.2,  # would normally ask a clarifying question
            is_advice_request=False,
            needs_clarification=False,
            standalone_query="Analyze the portfolio in this screenshot.",
            tickers=[],
        )
    )
    shot = ScreenshotRead(
        turn_id="turn-1", status="read", holdings=[ScreenshotHolding(symbol="VTI", quantity=1)]
    )
    update = await RouterNode(gw, WorkflowConfig())(turn(screenshot=shot))
    plan: RoutePlan = update["plan"]
    assert plan.agents == [AgentName.PORTFOLIO, AgentName.FINANCE_QA]
    assert not plan.needs_clarification
    assert "screenshot in this conversation: yes" in model.calls[0][-1].text


async def test_advice_with_a_screenshot_still_redirects() -> None:
    shot = ScreenshotRead(turn_id="turn-1", status="read")
    update = await RouterNode(LLMGateway([]), WorkflowConfig())(
        turn("Should I sell these?", screenshot=shot)
    )
    assert update["plan"].is_advice_request
