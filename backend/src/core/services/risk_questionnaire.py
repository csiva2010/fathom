"""Risk questionnaire (GL-01): six questions that place a user in a risk profile.

Each option carries 0 to 3 points; the total (0 to 18) maps to conservative, moderate or
aggressive. Time horizon and reaction to losses matter most, as in common brokerage
questionnaires. The result is an educational label used to pick illustrative return
assumptions and example mixes, not a suitability assessment.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from src.core.domain.risk import RiskProfile
from src.core.errors import ValidationFailed

# Totals at or below these are conservative / moderate; anything higher is aggressive.
CONSERVATIVE_MAX_SCORE = 6
MODERATE_MAX_SCORE = 12


class RiskOption(BaseModel):
    id: str
    label: str
    points: int


class RiskQuestion(BaseModel):
    id: str
    prompt: str
    options: list[RiskOption]


class RiskResult(BaseModel):
    score: int
    max_score: int
    risk_profile: RiskProfile


def _options(*labels: str) -> list[RiskOption]:
    return [RiskOption(id=chr(ord("a") + i), label=text, points=i) for i, text in enumerate(labels)]


QUESTIONS: list[RiskQuestion] = [
    RiskQuestion(
        id="horizon",
        prompt="When do you expect to need most of the money you're investing?",
        options=_options(
            "Within 3 years", "In 3 to 7 years", "In 7 to 15 years", "More than 15 years away"
        ),
    ),
    RiskQuestion(
        id="drop_reaction",
        prompt="Your investments fall 20% in a month. What would you most likely do?",
        options=_options(
            "Sell everything to stop further losses",
            "Sell some to reduce the risk",
            "Hold and wait for a recovery",
            "Invest more while prices are lower",
        ),
    ),
    RiskQuestion(
        id="goal",
        prompt="Which matters most to you for this money?",
        options=_options(
            "Not losing any of it",
            "Steady income with little ups and downs",
            "A balance of growth and stability",
            "As much long-term growth as possible",
        ),
    ),
    RiskQuestion(
        id="emergency_fund",
        prompt="How many months of expenses do you have set aside for emergencies?",
        options=_options("None", "Less than 3 months", "3 to 6 months", "More than 6 months"),
    ),
    RiskQuestion(
        id="experience",
        prompt="How much investing experience do you have?",
        options=_options(
            "None yet",
            "Savings accounts and CDs",
            "Some funds or a workplace retirement plan",
            "Several years with stocks and funds",
        ),
    ),
    RiskQuestion(
        id="swings",
        prompt="Which yearly range of outcomes would you be most comfortable with?",
        options=_options(
            "Between +2% and -1%",
            "Between +8% and -5%",
            "Between +15% and -12%",
            "Between +30% and -25%",
        ),
    ),
]

MAX_SCORE = sum(max(o.points for o in q.options) for q in QUESTIONS)


def profile_for_score(score: int) -> RiskProfile:
    if score <= CONSERVATIVE_MAX_SCORE:
        return RiskProfile.CONSERVATIVE
    if score <= MODERATE_MAX_SCORE:
        return RiskProfile.MODERATE
    return RiskProfile.AGGRESSIVE


def score_answers(answers: Mapping[str, str]) -> RiskResult:
    """Score a complete set of answers ({question id: option id})."""
    unknown = sorted(set(answers) - {q.id for q in QUESTIONS})
    if unknown:
        raise ValidationFailed(f"Unknown questions: {', '.join(unknown)}.")
    score = 0
    for question in QUESTIONS:
        choice = answers.get(question.id)
        if choice is None:
            raise ValidationFailed("Please answer every question.")
        option = next((o for o in question.options if o.id == choice), None)
        if option is None:
            raise ValidationFailed(f"'{choice}' isn't an option for '{question.prompt}'")
        score += option.points
    return RiskResult(score=score, max_score=MAX_SCORE, risk_profile=profile_for_score(score))
