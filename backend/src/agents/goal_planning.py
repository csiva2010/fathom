"""Goal Planning agent (AG-04, GL-02 to GL-04): projections at the user's risk level.

Saved goals are projected up front with `project_goal` (three return scenarios, inflation-
adjusted values and the monthly amount needed). For a goal described only in the chat,
the LLM extracts the inputs and calls the same function as a tool; it never does the math.
Example allocations are generic textbook mixes, labelled as education (GL-04).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from src.agents.base_agent import AgentRun, AgentTool, BaseAgent, Prepared, as_data, to_json
from src.core.domain.goals import GoalProjection, ProjectionRequest, Scenario
from src.core.domain.risk import RiskProfile
from src.core.errors import ValidationFailed
from src.core.llm import LLMGateway
from src.core.services.projections import example_allocation, project_goal
from src.utils.money import format_usd
from src.workflow.state import AgentName, Artifact, FinanceState, GoalSnapshot

MAX_GOALS = 3
DEFAULT_PROFILE = RiskProfile.MODERATE

NO_GOALS_ANSWER = (
    "You don't have any saved goals yet. To project one, tell me the target amount, the "
    "date you need it by, what you've saved so far and how much you can add each month "
    '(for example "$40,000 for a house by June 2030, $8,000 saved, $500 a month").'
)
NO_GOALS_CONTEXT = (
    "The user has no saved goals. If the question gives a target amount and a date, call "
    "project_goal with those inputs (savings and monthly amount default to 0 if not given). "
    "If inputs are missing, explain which ones you need."
)


class ProjectGoalArgs(BaseModel):
    target_amount: float = Field(gt=0, description="Amount needed, in US dollars")
    target_date: date = Field(description="When the money is needed (YYYY-MM-DD)")
    current_savings: float = Field(default=0, ge=0, description="Saved so far, in dollars")
    monthly_contribution: float = Field(default=0, ge=0, description="Added each month")
    risk_profile: RiskProfile | None = Field(
        default=None, description="Only if the user names one; otherwise their saved profile"
    )


class AllocationArgs(BaseModel):
    risk_profile: RiskProfile | None = Field(
        default=None, description="Profile to illustrate; defaults to the user's"
    )


def projection_facts(projection: GoalProjection) -> dict[str, Any]:
    return {
        "months": projection.months,
        "target_amount": projection.target_amount,
        "target_in_todays_dollars": projection.target_amount_real,
        "total_contributed": projection.total_contributed,
        "scenarios": [
            {
                "scenario": s.scenario.value,
                "annual_return_percent": s.annual_return_percent,
                "final_value": s.final_value,
                "final_value_in_todays_dollars": s.final_value_real,
                "reaches_target": s.reaches_target,
                "shortfall": s.shortfall,
                "monthly_needed_to_reach_target": s.required_monthly_contribution,
            }
            for s in projection.scenarios
        ],
        "assumptions": projection.assumptions,
    }


def _label(goal_type: str) -> str:
    return f"{goal_type.replace('_', ' ').capitalize()} goal"


class GoalPlanningAgent(BaseAgent):
    name = AgentName.GOAL
    role_prompt = """You are the Goal Planning agent. You help users understand whether a \
savings goal looks reachable and what drives the result.
- Use only the projection figures you were given or got from tools. Explain the three \
scenarios, what "in today's dollars" means, and the monthly amount each scenario needs.
- Stress that returns are illustrative assumptions, not predictions.
- Example allocations are generic textbook mixes for a risk level. Present them as \
education, never as what this user should hold.
- Call tools only for projections you don't already have."""

    def __init__(
        self,
        gateway: LLMGateway,
        *,
        today: Callable[[], date] = date.today,
        **kwargs: int,
    ):
        super().__init__(gateway, **kwargs)
        self._today = today

    def tools(self) -> Sequence[AgentTool]:
        return (
            AgentTool(
                "project_goal",
                "Project a savings goal under three return scenarios (adds a chart).",
                ProjectGoalArgs,
                self._project_tool,
            ),
            AgentTool(
                "example_allocation",
                "Generic textbook stock/bond/cash mix for a risk profile (education only).",
                AllocationArgs,
                self._allocation_tool,
            ),
        )

    # --- Prefetch ------------------------------------------------------------

    async def prepare(self, state: FinanceState, run: AgentRun) -> Prepared:
        user = state.get("user")
        saved_profile = user.risk_profile if user else None
        profile = saved_profile or DEFAULT_PROFILE
        run.inputs["risk_profile"] = profile

        goals = (state.get("goals") or [])[:MAX_GOALS]
        context: dict[str, Any] = {
            "risk_profile": profile.value,
            "risk_profile_is_default": saved_profile is None,
            "today": self._today().isoformat(),
        }
        projected: list[tuple[GoalSnapshot, GoalProjection]] = []
        skipped: list[str] = []
        for goal in goals:
            try:
                projection = self._project(
                    run,
                    ProjectionRequest(
                        target_amount=goal.target_amount,
                        target_date=goal.target_date,
                        current_savings=goal.current_savings,
                        monthly_contribution=goal.monthly_contribution,
                        risk_profile=profile,
                    ),
                    title=_label(goal.type),
                )
            except ValidationFailed as error:
                skipped.append(f"{_label(goal.type)}: {error.message}")
                continue
            projected.append((goal, projection))

        if goals:
            context["goals"] = [
                {
                    "goal": _label(goal.type),
                    "target_date": goal.target_date.isoformat(),
                    "current_savings": goal.current_savings,
                    "monthly_contribution": goal.monthly_contribution,
                    **projection_facts(projection),
                }
                for goal, projection in projected
            ]
            if skipped:
                context["goals_not_projected"] = skipped
            text = as_data("goal_projections", to_json(context))
        else:
            text = f"{as_data('user_profile', to_json(context))}\n\n{NO_GOALS_CONTEXT}"
        return Prepared(
            context=text,
            data={"projected": projected, "skipped": skipped, "profile": profile},
        )

    def _project(self, run: AgentRun, request: ProjectionRequest, *, title: str) -> GoalProjection:
        projection = project_goal(request, self._today())
        run.artifacts.append(
            Artifact(
                kind="projection",
                title=title,
                data={
                    "risk_profile": request.risk_profile.value,
                    "current_savings": request.current_savings,
                    "monthly_contribution": request.monthly_contribution,
                    "target_date": request.target_date.isoformat(),
                    **projection.model_dump(mode="json"),
                },
            )
        )
        return projection

    # --- Tools ---------------------------------------------------------------

    async def _project_tool(self, run: AgentRun, args: ProjectGoalArgs) -> str:
        request = ProjectionRequest(
            target_amount=args.target_amount,
            target_date=args.target_date,
            current_savings=args.current_savings,
            monthly_contribution=args.monthly_contribution,
            risk_profile=args.risk_profile or run.inputs.get("risk_profile", DEFAULT_PROFILE),
        )
        projection = self._project(run, request, title="Your goal")
        return to_json(projection_facts(projection))

    async def _allocation_tool(self, run: AgentRun, args: AllocationArgs) -> str:
        profile = args.risk_profile or run.inputs.get("risk_profile", DEFAULT_PROFILE)
        allocation = example_allocation(profile)
        run.artifacts.append(
            Artifact(
                kind="example_allocation",
                title=f"Example {profile.value} mix",
                data=allocation.model_dump(mode="json"),
            )
        )
        return to_json(allocation.model_dump(mode="json"))

    # --- Without an LLM ------------------------------------------------------

    def offline_answer(self, state: FinanceState, run: AgentRun, prepared: Prepared) -> str:
        projected: list[tuple[GoalSnapshot, GoalProjection]] = prepared.data.get("projected", [])
        skipped: list[str] = prepared.data.get("skipped", [])
        if not projected and not skipped:
            return NO_GOALS_ANSWER
        profile: RiskProfile = prepared.data["profile"]
        lines: list[str] = []
        for goal, projection in projected:
            by_name = {s.scenario: s for s in projection.scenarios}
            expected = by_name[Scenario.EXPECTED]
            outcome = (
                "reaches the target"
                if expected.reaches_target
                else f"falls short by {format_usd(expected.shortfall, decimals=0)}"
            )
            monthly = format_usd(goal.monthly_contribution, decimals=0)
            lines.append(
                f"**{_label(goal.type)}** ({format_usd(goal.target_amount, decimals=0)} by "
                f"{goal.target_date:%B %Y}): adding {monthly} "
                f"a month, the expected scenario ({expected.annual_return_percent:g}% a year) "
                f"ends near {format_usd(expected.final_value, decimals=0)} and {outcome}. "
                "Reaching it in that scenario takes about "
                f"{format_usd(expected.required_monthly_contribution, decimals=0)} a month."
            )
        lines.extend(f"- {note}" for note in skipped)
        lines.append(
            f"These use illustrative returns for a {profile.value} mix, not predictions; the "
            "pessimistic and optimistic scenarios show how much the result can vary."
        )
        return "\n\n".join(lines)

    def confidence(self, run: AgentRun, prepared: Prepared) -> float:
        return 0.85 if run.artifacts else 0.5

    def follow_ups(self, state: FinanceState, run: AgentRun, prepared: Prepared) -> list[str]:
        return [
            "Why do the three scenarios differ so much?",
            "What does inflation do to a long-term goal?",
            "What does a typical mix for my risk level look like?",
        ]
