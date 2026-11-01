"""Current user and profile (AU-03, UI-02)."""

from __future__ import annotations

from fastapi import APIRouter

from src.core.domain.risk import RiskProfile
from src.core.services.risk_questionnaire import QUESTIONS, score_answers
from src.data.db.models import Profile
from src.data.db.repositories.user_repository import ProfileRepository
from src.web_app.auth.current_user import CurrentUser, CurrentUserDep
from src.web_app.dependencies import DbDep
from src.web_app.schemas.user import (
    ExperienceLevel,
    MeOut,
    ProfileOut,
    ProfileUpdate,
    RiskAnswers,
    RiskAssessmentOut,
    RiskQuestionnaireOut,
)

router = APIRouter(prefix="/me", tags=["me"])


def _to_me(user: CurrentUser, profile: Profile) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        is_guest=user.is_guest,
        profile=ProfileOut(
            experience_level=ExperienceLevel(profile.experience_level),
            risk_profile=RiskProfile(profile.risk_profile) if profile.risk_profile else None,
            risk_answers=profile.risk_answers,
            disclaimer_accepted_at=profile.disclaimer_accepted_at,
            onboarding_complete=bool(profile.disclaimer_accepted_at and profile.risk_profile),
        ),
    )


@router.get("", response_model=MeOut, summary="Current user and profile")
def get_me(user: CurrentUserDep, db: DbDep) -> MeOut:
    profile = ProfileRepository(db).get_or_create(user.id)
    db.commit()
    return _to_me(user, profile)


@router.put("/profile", response_model=MeOut, summary="Update onboarding answers")
def update_profile(body: ProfileUpdate, user: CurrentUserDep, db: DbDep) -> MeOut:
    profile = ProfileRepository(db).update(
        user.id,
        experience_level=body.experience_level.value if body.experience_level else None,
        risk_profile=body.risk_profile.value if body.risk_profile else None,
        risk_answers=body.risk_answers,
        accept_disclaimer=body.accept_disclaimer,
    )
    db.commit()
    return _to_me(user, profile)


@router.get(
    "/risk-questionnaire", response_model=RiskQuestionnaireOut, summary="Risk profile questions"
)
def get_risk_questionnaire(_user: CurrentUserDep) -> RiskQuestionnaireOut:
    return RiskQuestionnaireOut(questions=QUESTIONS)


@router.post(
    "/risk-questionnaire",
    response_model=RiskAssessmentOut,
    summary="Score the questionnaire and save the risk profile (GL-01)",
)
def submit_risk_questionnaire(
    body: RiskAnswers, user: CurrentUserDep, db: DbDep
) -> RiskAssessmentOut:
    result = score_answers(body.answers)
    profile = ProfileRepository(db).update(
        user.id, risk_profile=result.risk_profile.value, risk_answers=body.answers
    )
    db.commit()
    return RiskAssessmentOut(result=result, me=_to_me(user, profile))
