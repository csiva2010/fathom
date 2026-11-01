"""Router node: classify a message into a plan of agents (OR-01 to OR-03, CH-02).

The LLM returns a structured `RouterDecision`: agents, confidence, advice flag, tickers
and a standalone rewrite of the question that resolves "it"/"that ETF" from history. Two
deterministic layers sit around it:
- an advice detector that flags "should I buy NVDA?" even if the model misses it (OR-03);
- a keyword router used when no LLM is available, so the graph still routes (OR-07).
Confidence below the configured threshold turns into a clarifying question (OR-02).
"""

from __future__ import annotations

import re
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.core.config.settings import WorkflowConfig
from src.core.errors import LLMUnavailable
from src.core.llm import LLMGateway
from src.core.logging import get_logger
from src.workflow.context import latest_user_text, recent_history
from src.workflow.state import AgentName, FinanceState, RoutePlan, TraceEvent

log = get_logger(__name__)

ADVICE_PATTERN = re.compile(
    r"\b(should|shall|must|do) (i|we) (buy|sell|hold|short|dump|keep|invest in|get into|"
    r"put (my )?money (in|into))\b"
    r"|\bis (it )?(a )?(good|bad|smart|great) (time )?(to )?(buy|sell|investment)\b"
    r"|\b(is|are) [\w$.]+ (stock |shares )?(a )?(good|bad|great|smart) (buy|investment|stock)\b"
    r"|\bwhat (stocks?|etfs?|funds?|crypto) should (i|we)\b"
    r"|\bwhich (stocks?|etfs?|funds?) (should (i|we) |to )(buy|pick|choose|invest)\b"
    r"|\b(buy|sell),? (or|vs\.?) (hold|sell|buy)\b"
    r"|\bworth (buying|investing in|selling)\b"
    r"|\b(where|how) should (i|we) (invest|put) my\b"
    r"|\b(recommend|tell me) (a |some |which )?(stocks?|etfs?|funds?) to buy\b",
    re.IGNORECASE,
)

_TICKER = re.compile(r"(?<![\w$])\$?([A-Z]{1,5}(?:\.[A-Z])?)(?![\w])")
_TICKER_SHAPE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")
# Upper-case words that look like tickers but are not (unless written with a $ prefix).
_COMMON_CAPS = """
I A AN AM AS AT BE BY DO GO HE IF IN IS IT ME MY NO OF OK ON OR SO TO UP US WE ETF
ETFS IRA IRAS ROTH HSA FSA USA USD CEO CFO IPO SEC FAQ GDP CPI FED EPS PE YTD AI
APR APY CD CDS FDIC FINRA IRS LLC NAV REIT REITS RMD SIPC TIPS ESG DCA EFT ATM IOU
S P DOW NYSE VS AND THE WHAT HOW WHY WHO WHEN BUY SELL HOLD LOL UK EU OTC K Q
"""
_NOT_TICKERS = frozenset(_COMMON_CAPS.split())
_REFERENCE = re.compile(r"\b(it|its|it's|that|this|they|them|those|these|same)\b", re.I)

_KEYWORDS: dict[AgentName, re.Pattern[str]] = {
    AgentName.MARKET: re.compile(
        r"\b(price|quote|trading at|market (today|now|overview)|how('s| is) the market|"
        r"index|indices|s&p|nasdaq|dow|movers?|gainers?|losers?|sectors?|moving average|"
        r"52[- ]week|volatil\w*|chart|performance|doing today|up today|down today)\b",
        re.I,
    ),
    AgentName.PORTFOLIO: re.compile(
        r"\b(my (portfolio|holdings|positions|investments|allocation)|diversified enough|"
        r"concentrat\w+ in my)\b",
        re.I,
    ),
    AgentName.GOAL: re.compile(
        r"\b(goal|save for|saving for|retire (by|at|early)|down payment|on track|"
        r"how much (do|should|would) i (need|save)|projection|monthly contribution)\b",
        re.I,
    ),
    AgentName.NEWS: re.compile(
        r"\b(news|headlines?|why did \S+ (fall|drop|rise|jump|surge|plunge)|earnings report)\b",
        re.I,
    ),
    AgentName.TAX: re.compile(
        r"\b(tax\w*|roth|ira|401\(?k\)?|403\(?b\)?|hsa|529|capital gains?|wash sale|"
        r"deduct\w*|rmd)\b",
        re.I,
    ),
}

AGENT_GUIDE = """Agents you can route to:
- finance_qa: explains finance concepts and terms (what is an ETF, how bonds work).
- market_analysis: current quotes, price history, indices, sectors, movers, moving averages
  and volatility for specific tickers or the overall market.
- portfolio_analysis: analyzes the user's saved portfolio (value, allocation, risk, fees).
- goal_planning: goal projections, required monthly savings, allocations by risk profile.
- news_synthesizer: recent news for a ticker or the market and why it matters.
- tax_education: US account types (401(k), IRA, Roth, HSA, 529), capital gains, wash sales."""

ROUTER_PROMPT = f"""You route messages for an educational finance assistant.
{AGENT_GUIDE}

Return:
- agents: one or more agents. Use several only when the question truly has several parts
  (e.g. "is my portfolio on track for my house goal?" -> portfolio_analysis + goal_planning).
- confidence: 0 to 1, how sure you are about the routing and what the user wants.
- is_advice_request: true if the user asks whether to buy, sell or hold a specific
  security, or asks which specific investment to pick.
- needs_clarification + clarifying_question: only if you cannot tell what they want.
- standalone_query: the question rewritten to stand alone, with pronouns like "it" or
  "that ETF" replaced by what they refer to in the conversation.
- tickers: US stock or ETF tickers the question is about, including ones referred to
  indirectly. Empty if none."""


class RouterDecision(BaseModel):
    """Structured output the router LLM fills in."""

    agents: list[AgentName] = Field(description="Agents that should answer, most relevant first")
    confidence: float = Field(ge=0, le=1, description="Routing confidence from 0 to 1")
    is_advice_request: bool = Field(
        description="True if the user asks whether to buy, sell or hold a specific security"
    )
    needs_clarification: bool = Field(description="True if the request is too unclear")
    clarifying_question: str | None = Field(
        default=None, description="A short question to ask the user when clarification is needed"
    )
    standalone_query: str = Field(description="The question rewritten to stand alone")
    tickers: list[str] = Field(default_factory=list, description="Ticker symbols in scope")


def looks_like_advice_request(text: str) -> bool:
    return bool(ADVICE_PATTERN.search(text))


def extract_tickers(text: str) -> list[str]:
    found: list[str] = []
    for match in _TICKER.finditer(text):
        symbol = match.group(1)
        explicit = match.group(0).startswith("$")
        if (explicit or symbol not in _NOT_TICKERS) and symbol not in found:
            found.append(symbol)
    return found


def clean_tickers(raw: list[str], limit: int) -> list[str]:
    tickers: list[str] = []
    for item in raw:
        symbol = item.strip().lstrip("$").upper()
        if _TICKER_SHAPE.match(symbol) and symbol not in tickers:
            tickers.append(symbol)
    return tickers[:limit]


def rule_based_decision(text: str, focus: list[str]) -> RouterDecision:
    """Keyword routing used when the LLM is unavailable."""
    tickers = extract_tickers(text)
    if not tickers and focus and _REFERENCE.search(text):
        tickers = list(focus)
    agents = [agent for agent, pattern in _KEYWORDS.items() if pattern.search(text)]
    if tickers and not agents:
        agents = [AgentName.MARKET]
    if not agents:
        agents = [AgentName.FINANCE_QA]
    return RouterDecision(
        agents=agents,
        confidence=0.7 if len(text.split()) >= 2 else 0.4,
        is_advice_request=looks_like_advice_request(text),
        needs_clarification=False,
        standalone_query=text,
        tickers=tickers,
    )


class RouterNode:
    def __init__(self, gateway: LLMGateway, config: WorkflowConfig):
        self._gateway = gateway
        self._config = config

    async def __call__(self, state: FinanceState) -> dict[str, Any]:
        started = time.perf_counter()
        text = latest_user_text(state)
        focus = list(state.get("focus_tickers") or [])

        method = "llm"
        try:
            decision = await self._gateway.astructured(RouterDecision, self._messages(state, focus))
        except LLMUnavailable:
            method = "rules"
            decision = rule_based_decision(text, focus)

        plan = self._plan(decision, text, method)
        new_focus = plan.tickers or focus
        log.info(
            "routed",
            extra={
                "agents": [a.value for a in plan.agents],
                "confidence": plan.confidence,
                "advice": plan.is_advice_request,
                "clarify": plan.needs_clarification,
                "method": method,
            },
        )
        return {
            "plan": plan,
            "focus_tickers": new_focus,
            "trace": [
                TraceEvent(
                    node="router",
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    detail={
                        "method": method,
                        "agents": [a.value for a in plan.agents],
                        "confidence": plan.confidence,
                        "tickers": plan.tickers,
                    },
                )
            ],
        }

    def _messages(self, state: FinanceState, focus: list[str]) -> list[Any]:
        portfolio = state.get("portfolio")
        context = [
            f"Tickers discussed recently: {', '.join(focus) or 'none'}",
            f"User has a saved portfolio: {'yes' if portfolio else 'no'}",
            f"User has saved goals: {'yes' if state.get('goals') else 'no'}",
        ]
        history = recent_history(state, self._config.history_messages)
        transcript = "\n".join(
            f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.text[:500]}"
            for m in history
        )
        prompt = "\n".join(context)
        if transcript:
            prompt += f"\n\nConversation so far:\n{transcript}"
        prompt += f"\n\nNew message: {latest_user_text(state)}"
        return [SystemMessage(ROUTER_PROMPT), HumanMessage(prompt)]

    def _plan(self, decision: RouterDecision, text: str, method: str) -> RoutePlan:
        agents: list[AgentName] = []
        for agent in decision.agents:
            if agent not in agents:
                agents.append(agent)
        agents = agents[: self._config.max_agents_per_turn] or [AgentName.FINANCE_QA]

        is_advice = decision.is_advice_request or looks_like_advice_request(text)
        clarify = not is_advice and (
            decision.needs_clarification
            or decision.confidence < self._config.clarify_below_confidence
        )
        question = (decision.clarifying_question or "").strip() or (
            "Could you tell me a bit more about what you'd like to know? For example, a "
            "concept to explain, a ticker to look up, or a goal to plan."
        )
        return RoutePlan(
            agents=agents,
            confidence=decision.confidence,
            needs_clarification=clarify,
            clarifying_question=question if clarify else None,
            is_advice_request=is_advice,
            standalone_query=decision.standalone_query.strip() or text,
            tickers=clean_tickers(decision.tickers, self._config.max_focus_tickers),
            method="rules" if method == "rules" else "llm",
        )
