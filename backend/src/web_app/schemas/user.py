from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.core.domain.risk import RiskProfile
from src.core.services.risk_questionnaire import RiskQuestion, RiskResult


class ExperienceLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ProfileOut(BaseModel):
    experience_level: ExperienceLevel
    risk_profile: RiskProfile | None
    risk_answers: dict[str, Any] | None
    disclaimer_accepted_at: datetime | None
    onboarding_complete: bool


class MeOut(BaseModel):
    id: str
    email: str
    name: str
    avatar_url: str | None
    is_guest: bool
    profile: ProfileOut


class ProfileUpdate(BaseModel):
    experience_level: ExperienceLevel | None = None
    risk_profile: RiskProfile | None = None
    risk_answers: dict[str, int | str] | None = Field(default=None, max_length=20)
    accept_disclaimer: bool | None = None


class RiskQuestionnaireOut(BaseModel):
    questions: list[RiskQuestion]


class RiskAnswers(BaseModel):
    """Question id -> chosen option id, for every question (GL-01)."""

    answers: dict[str, str] = Field(max_length=20)


class RiskAssessmentOut(BaseModel):
    result: RiskResult
    me: MeOut
