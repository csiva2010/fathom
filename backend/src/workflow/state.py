"""Typed graph state and agent contracts shared by every workflow node (OR-04, OR-05).

Agents never call each other: they read `FinanceState` and return an `AgentOutput`, which
the parallel-safe reducer appends to `agent_outputs`. Per-turn lists are cleared at the
start of each turn (a `Fresh` update replaces them) so a checkpointed thread keeps its
messages and context but not the previous turn's outputs.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Literal, TypedDict, TypeVar

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from src.core.domain.market import AssetClass, DataStatus, Freshness
from src.core.domain.portfolio import HoldingInput
from src.core.domain.risk import RiskProfile
from src.rag.models import Citation

T = TypeVar("T")


class Fresh(list[T]):
    """A list update that replaces the current value instead of appending to it."""


def per_turn(left: list[T] | None, right: list[T]) -> list[T]:
    """Append reducer for per-turn lists; a `Fresh` update starts the list over."""
    if isinstance(right, Fresh):
        return list(right)
    return [*(left or []), *right]


class AgentName(StrEnum):
    FINANCE_QA = "finance_qa"
    PORTFOLIO = "portfolio_analysis"
    MARKET = "market_analysis"
    GOAL = "goal_planning"
    NEWS = "news_synthesizer"
    TAX = "tax_education"

    @property
    def label(self) -> str:
        return {
            AgentName.FINANCE_QA: "Finance Q&A",
            AgentName.PORTFOLIO: "Portfolio Analysis",
            AgentName.MARKET: "Market Analysis",
            AgentName.GOAL: "Goal Planning",
            AgentName.NEWS: "News Synthesizer",
            AgentName.TAX: "Tax Education",
        }[self]


class UserContext(BaseModel):
    user_id: str
    experience_level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    risk_profile: RiskProfile | None = None


class PortfolioSnapshot(BaseModel):
    id: str
    name: str
    holdings: list[HoldingInput] = Field(default_factory=list)


class GoalSnapshot(BaseModel):
    id: str
    type: str
    target_amount: float
    target_date: date
    current_savings: float = 0
    monthly_contribution: float = 0


class RoutePlan(BaseModel):
    """Router output (OR-01): which agents run, and the question they should answer."""

    agents: list[AgentName] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    needs_clarification: bool = False
    clarifying_question: str | None = None
    is_advice_request: bool = False
    standalone_query: str = ""
    tickers: list[str] = Field(default_factory=list)
    method: Literal["llm", "rules"] = "llm"


class Artifact(BaseModel):
    """Chart or table payload the UI renders next to an answer (CH-06)."""

    kind: Literal[
        "quote_card",
        "price_chart",
        "indicators",
        "index_cards",
        "movers",
        "sector_table",
        "portfolio_metrics",
        "allocation",
        "projection",
        "example_allocation",
        "news_list",
    ]
    title: str
    data: dict[str, Any]


class AgentOutput(BaseModel):
    agent: AgentName
    answer_md: str
    citations: list[Citation] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    freshness: list[Freshness] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    follow_ups: list[str] = Field(default_factory=list)
    grounded: bool = False  # answer rests on KB sources (compliance expects citations)


class NodeError(BaseModel):
    node: str
    code: str
    message: str
    retryable: bool = False


class TraceEvent(BaseModel):
    """One node's timing and details for logs and the "How I answered" panel (OR-08)."""

    node: str
    latency_ms: int
    detail: dict[str, Any] = Field(default_factory=dict)


class ComplianceReport(BaseModel):
    passed: bool = True
    issues: list[str] = Field(default_factory=list)
    rewritten: bool = False
    disclaimer_added: bool = False


class FinalAnswer(BaseModel):
    kind: Literal["answer", "clarification", "redirect"] = "answer"
    answer_md: str
    agents: list[AgentName] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    freshness: list[Freshness] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    compliance: ComplianceReport = Field(default_factory=ComplianceReport)


class FinanceState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    turn_id: str  # id the caller gives this turn's answer message (CH-08 feedback, history)
    user: UserContext
    portfolio: PortfolioSnapshot | None
    goals: list[GoalSnapshot]
    focus_tickers: list[str]
    plan: RoutePlan | None
    agent_outputs: Annotated[list[AgentOutput], per_turn]
    errors: Annotated[list[NodeError], per_turn]
    notes: Annotated[list[str], per_turn]
    trace: Annotated[list[TraceEvent], per_turn]
    draft: FinalAnswer | None
    final: FinalAnswer | None


# Types a checkpoint may contain. The checkpointer only deserializes listed types, so add
# any new model that goes into FinanceState here.
CHECKPOINT_TYPES: tuple[type, ...] = (
    UserContext,
    PortfolioSnapshot,
    GoalSnapshot,
    RoutePlan,
    AgentOutput,
    Artifact,
    NodeError,
    TraceEvent,
    ComplianceReport,
    FinalAnswer,
    AgentName,
    Citation,
    Freshness,
    DataStatus,
    HoldingInput,
    AssetClass,
    RiskProfile,
    Fresh,
)
