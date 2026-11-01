"""Goals and projections (GL-02 to GL-04, UI-06).

Projections come from the pure `project_goal` service, never from the browser, so the
Goals view, the chat's Goal agent and the MCP tools all show the same numbers. The
`/goals/project` route is stateless: the contribution slider calls it as it moves.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Response, status

from src.core.domain.goals import ProjectionRequest
from src.core.domain.risk import RiskProfile
from src.core.errors import ValidationFailed
from src.core.services.projections import example_allocation, project_goal
from src.data.db.models import Goal
from src.data.db.repositories.goal_repository import GoalFields, GoalRepository
from src.data.db.repositories.user_repository import ProfileRepository
from src.web_app.auth.current_user import CurrentUser, CurrentUserDep
from src.web_app.dependencies import DbDep
from src.web_app.schemas.goals import GoalIn, GoalList, GoalOut, GoalType, ProjectionOut

router = APIRouter(prefix="/goals", tags=["goals"])


def _request(goal: Goal | GoalIn, profile: RiskProfile) -> ProjectionRequest:
    return ProjectionRequest(
        target_amount=goal.target_amount,
        target_date=goal.target_date,
        current_savings=goal.current_savings,
        monthly_contribution=goal.monthly_contribution,
        risk_profile=profile,
    )


def _out(goal: Goal) -> GoalOut:
    profile = RiskProfile(goal.risk_profile)
    projection, error = None, None
    try:
        projection = project_goal(_request(goal, profile), date.today())
    except ValidationFailed as failure:
        error = failure.message
    return GoalOut(
        id=goal.id,
        type=GoalType(goal.type),
        name=goal.name,
        target_amount=goal.target_amount,
        target_date=goal.target_date,
        current_savings=goal.current_savings,
        monthly_contribution=goal.monthly_contribution,
        risk_profile=profile,
        created_at=goal.created_at,
        projection=projection,
        projection_error=error,
    )


def _fields(body: GoalIn, user: CurrentUser, db: DbDep) -> GoalFields:
    """Validated columns; the goal must be projectable (a future date within 70 years)."""
    saved = ProfileRepository(db).get_or_create(user.id).risk_profile
    profile = body.risk_profile or (RiskProfile(saved) if saved else RiskProfile.MODERATE)
    project_goal(_request(body, profile), date.today())  # raises ValidationFailed
    return GoalFields(
        type=body.type.value,
        name=body.name.strip(),
        target_amount=body.target_amount,
        target_date=body.target_date,
        current_savings=body.current_savings,
        monthly_contribution=body.monthly_contribution,
        risk_profile=profile.value,
    )


@router.get("", response_model=GoalList, summary="Your goals with their projections")
def list_goals(user: CurrentUserDep, db: DbDep) -> GoalList:
    return GoalList(goals=[_out(g) for g in GoalRepository(db).list_for(user.id)])


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED, summary="Add a goal")
def create_goal(body: GoalIn, user: CurrentUserDep, db: DbDep) -> GoalOut:
    goal = GoalRepository(db).create(user.id, _fields(body, user, db))
    db.commit()
    return _out(goal)


@router.post("/project", response_model=ProjectionOut, summary="Project goal inputs (live slider)")
def project(body: ProjectionRequest, _user: CurrentUserDep) -> ProjectionOut:
    return ProjectionOut(
        projection=project_goal(body, date.today()),
        example_allocation=example_allocation(body.risk_profile),
    )


@router.put("/{goal_id}", response_model=GoalOut, summary="Update a goal")
def update_goal(goal_id: str, body: GoalIn, user: CurrentUserDep, db: DbDep) -> GoalOut:
    repo = GoalRepository(db)
    goal = repo.update(repo.get_owned(user.id, goal_id), _fields(body, user, db))
    db.commit()
    return _out(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a goal")
def delete_goal(goal_id: str, user: CurrentUserDep, db: DbDep) -> Response:
    repo = GoalRepository(db)
    repo.delete(repo.get_owned(user.id, goal_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
