from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExperienceLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class RiskProfile(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


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
