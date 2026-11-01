"""User and profile persistence. Every lookup is keyed by the verified user id."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.data.db.base import new_id, utcnow
from src.data.db.models import Profile, User


@dataclass(frozen=True)
class GoogleIdentity:
    """The only Google account fields we keep (NF-S03)."""

    sub: str
    email: str
    name: str = ""
    avatar_url: str | None = None


class UserRepository:
    def __init__(self, session: Session):
        self._session = session

    def get(self, user_id: str) -> User | None:
        return self._session.get(User, user_id)

    def get_by_google_sub(self, google_sub: str) -> User | None:
        return self._session.scalar(select(User).where(User.google_sub == google_sub))

    def upsert_from_google(self, identity: GoogleIdentity) -> User:
        """Create the user on first sign-in, refresh name/email/avatar on later ones."""
        user = self.get_by_google_sub(identity.sub)
        if user is None:
            user = User(google_sub=identity.sub, email=identity.email)
            user.profile = Profile()
            self._session.add(user)
        user.email = identity.email
        user.name = identity.name
        user.avatar_url = identity.avatar_url
        self._session.flush()
        return user

    def create_guest(self) -> User:
        """A fresh, isolated guest account. It lives as long as its session cookie does."""
        user = User(google_sub=f"guest:{new_id()}", email="", name="Guest", is_guest=True)
        user.profile = Profile()
        self._session.add(user)
        self._session.flush()
        return user


class ProfileRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_or_create(self, user_id: str) -> Profile:
        profile = self._session.get(Profile, user_id)
        if profile is None:
            profile = Profile(user_id=user_id)
            self._session.add(profile)
            self._session.flush()
        return profile

    def update(
        self,
        user_id: str,
        *,
        experience_level: str | None = None,
        risk_profile: str | None = None,
        risk_answers: Mapping[str, object] | None = None,
        accept_disclaimer: bool | None = None,
    ) -> Profile:
        profile = self.get_or_create(user_id)
        if experience_level is not None:
            profile.experience_level = experience_level
        if risk_profile is not None:
            profile.risk_profile = risk_profile
        if risk_answers is not None:
            profile.risk_answers = dict(risk_answers)
        if accept_disclaimer and profile.disclaimer_accepted_at is None:
            profile.disclaimer_accepted_at = utcnow()
        self._session.flush()
        return profile
