"""Load-context node and message helpers (OR-05, CH-02).

At the start of each turn the user's profile, most recent portfolio and goals are loaded
into state, and the per-turn fields are cleared. The user id comes from the verified
session the caller put in `state["user"]`, never from message text.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from src.core.domain.market import AssetClass
from src.core.domain.portfolio import HoldingInput
from src.core.domain.risk import RiskProfile
from src.core.errors import ValidationFailed
from src.core.logging import get_logger
from src.data.db.models import Goal, Portfolio, Profile
from src.workflow.state import (
    FinanceState,
    Fresh,
    GoalSnapshot,
    PortfolioSnapshot,
    UserContext,
)
from src.workflow.tracing import TraceStep, trace_step

log = get_logger(__name__)

LEVELS = ("beginner", "intermediate", "advanced")


def latest_user_text(state: FinanceState) -> str:
    for message in reversed(state.get("messages") or []):
        if isinstance(message, HumanMessage):
            return message.text.strip()
    return ""


def recent_history(state: FinanceState, limit: int) -> list[BaseMessage]:
    """Earlier user and assistant turns (not the current question), oldest first."""
    messages: list[AnyMessage] = list(state.get("messages") or [])
    if messages and isinstance(messages[-1], HumanMessage):
        messages = messages[:-1]
    turns: list[BaseMessage] = [
        m for m in messages if isinstance(m, HumanMessage | AIMessage) and m.text.strip()
    ]
    # Tool-call scaffolding never reaches the shared history; only final texts do.
    turns = [
        HumanMessage(m.text) if isinstance(m, HumanMessage) else AIMessage(m.text) for m in turns
    ]
    return turns[-limit:] if limit else []


@dataclass
class LoadedContext:
    user: UserContext
    portfolio: PortfolioSnapshot | None = None
    goals: list[GoalSnapshot] = field(default_factory=list)


class ContextLoader(Protocol):
    async def load(self, user: UserContext) -> LoadedContext: ...


class StaticContextLoader:
    """Uses the user context as given (tests, MCP, or callers that already loaded it)."""

    async def load(self, user: UserContext) -> LoadedContext:
        return LoadedContext(user=user)


class DbContextLoader:
    """Reads the profile, latest own portfolio and goals, scoped by user id (AU-03)."""

    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    async def load(self, user: UserContext) -> LoadedContext:
        return await asyncio.to_thread(self._load, user)

    def _load(self, user: UserContext) -> LoadedContext:
        with self._session_factory() as session:
            profile = session.get(Profile, user.user_id)
            if profile is not None:
                level = profile.experience_level
                risk = profile.risk_profile
                user = user.model_copy(
                    update={
                        "experience_level": level if level in LEVELS else user.experience_level,
                        "risk_profile": RiskProfile(risk)
                        if risk is not None and risk in RiskProfile.__members__.values()
                        else user.risk_profile,
                    }
                )
            portfolio = session.scalar(
                select(Portfolio)
                .where(Portfolio.user_id == user.user_id, Portfolio.is_sample.is_(False))
                .options(selectinload(Portfolio.holdings))
                .order_by(Portfolio.created_at.desc())
                .limit(1)
            )
            goals = session.scalars(
                select(Goal).where(Goal.user_id == user.user_id).order_by(Goal.target_date)
            ).all()
            return LoadedContext(
                user=user,
                portfolio=_portfolio_snapshot(portfolio) if portfolio else None,
                goals=[
                    GoalSnapshot(
                        id=g.id,
                        type=g.type,
                        target_amount=g.target_amount,
                        target_date=g.target_date,
                        current_savings=g.current_savings,
                        monthly_contribution=g.monthly_contribution,
                    )
                    for g in goals
                ],
            )


def _portfolio_snapshot(portfolio: Portfolio) -> PortfolioSnapshot:
    asset_classes = set(AssetClass.__members__.values())
    return PortfolioSnapshot(
        id=portfolio.id,
        name=portfolio.name,
        holdings=[
            HoldingInput(
                symbol=h.symbol,
                quantity=h.quantity,
                cost_basis=h.cost_basis,
                asset_class=AssetClass(h.asset_class) if h.asset_class in asset_classes else None,
            )
            for h in portfolio.holdings
        ],
    )


class LoadContextNode:
    def __init__(self, loader: ContextLoader, max_message_chars: int):
        self._loader = loader
        self._max_chars = max_message_chars

    async def __call__(self, state: FinanceState) -> dict[str, Any]:
        with trace_step("load_context") as step:
            return await self._load(state, step)

    async def _load(self, state: FinanceState, step: TraceStep) -> dict[str, Any]:
        user = state.get("user")
        if user is None:
            raise ValidationFailed("The workflow needs a signed-in user.")
        text = latest_user_text(state)
        if not text:
            raise ValidationFailed("Type a question to get started.")
        if len(text) > self._max_chars:
            raise ValidationFailed(f"Keep messages under {self._max_chars} characters.")

        loaded = await self._loader.load(user)
        return {
            "user": loaded.user,
            "portfolio": loaded.portfolio,
            "goals": loaded.goals,
            "plan": None,
            "draft": None,
            "final": None,
            # Fresh lists replace the previous turn's values (see state.per_turn).
            "agent_outputs": Fresh(),
            "errors": Fresh(),
            "notes": Fresh(),
            "trace": Fresh(
                [
                    step.event(
                        level=loaded.user.experience_level,
                        has_portfolio=loaded.portfolio is not None,
                        goals=len(loaded.goals),
                    )
                ]
            ),
        }
