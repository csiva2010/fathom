"""Goal persistence (GL-02). Every query is scoped by the owner's user id (AU-03)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.errors import NotFound
from src.data.db.models import Goal


@dataclass(frozen=True)
class GoalFields:
    type: str
    name: str
    target_amount: float
    target_date: date
    current_savings: float
    monthly_contribution: float
    risk_profile: str


class GoalRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_for(self, user_id: str) -> list[Goal]:
        stmt = (
            select(Goal).where(Goal.user_id == user_id).order_by(Goal.target_date, Goal.created_at)
        )
        return list(self._session.scalars(stmt))

    def get_owned(self, user_id: str, goal_id: str) -> Goal:
        goal = self._session.get(Goal, goal_id)
        if goal is None or goal.user_id != user_id:
            raise NotFound("That goal doesn't exist.")
        return goal

    def create(self, user_id: str, fields: GoalFields) -> Goal:
        goal = Goal(user_id=user_id, **fields.__dict__)
        self._session.add(goal)
        self._session.flush()
        return goal

    def update(self, goal: Goal, fields: GoalFields) -> Goal:
        for name, value in fields.__dict__.items():
            setattr(goal, name, value)
        self._session.flush()
        return goal

    def delete(self, goal: Goal) -> None:
        self._session.delete(goal)
        self._session.flush()
