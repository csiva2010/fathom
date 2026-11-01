from __future__ import annotations

from sqlalchemy.orm import Session

from src.data.db.repositories.portfolio_repository import HoldingInput, PortfolioRepository
from src.data.db.repositories.user_repository import (
    GoogleIdentity,
    ProfileRepository,
    UserRepository,
)


def test_upsert_creates_then_updates_user(db: Session) -> None:
    repo = UserRepository(db)
    user = repo.upsert_from_google(GoogleIdentity(sub="g1", email="old@x.com", name="Old"))
    assert user.profile is not None

    again = repo.upsert_from_google(
        GoogleIdentity(sub="g1", email="new@x.com", name="New", avatar_url="http://a")
    )
    assert again.id == user.id
    assert again.email == "new@x.com"
    assert repo.get(user.id) is again
    assert repo.get("missing") is None


def test_profile_update_sets_disclaimer_once(db: Session) -> None:
    user = UserRepository(db).upsert_from_google(GoogleIdentity(sub="g2", email="a@x.com"))
    profiles = ProfileRepository(db)
    profile = profiles.update(
        user.id,
        experience_level="intermediate",
        risk_profile="moderate",
        risk_answers={"q1": 3},
        accept_disclaimer=True,
    )
    accepted = profile.disclaimer_accepted_at
    assert accepted is not None
    assert profile.risk_answers == {"q1": 3}

    profile = profiles.update(user.id, accept_disclaimer=True)
    assert profile.disclaimer_accepted_at == accepted
    assert profile.experience_level == "intermediate"


def test_profile_get_or_create_for_user_without_profile(db: Session) -> None:
    user = UserRepository(db).upsert_from_google(GoogleIdentity(sub="g3", email="b@x.com"))
    db.delete(user.profile)
    db.flush()
    db.expire_all()
    assert ProfileRepository(db).get_or_create(user.id).experience_level == "beginner"


def test_sample_portfolio_upsert_is_idempotent(db: Session) -> None:
    repo = PortfolioRepository(db)
    repo.upsert_sample("Starter", "d", [HoldingInput("vti", 10)])
    repo.upsert_sample("Starter", "d2", [HoldingInput("VTI", 5), HoldingInput("BND", 3, 70.0)])
    db.commit()
    db.expire_all()
    samples = repo.list_samples()
    assert len(samples) == 1
    assert samples[0].description == "d2"
    assert [h.symbol for h in samples[0].holdings] == ["BND", "VTI"]


def test_create_guest_makes_distinct_users_with_profiles(db: Session) -> None:
    repo = UserRepository(db)
    a, b = repo.create_guest(), repo.create_guest()
    assert a.id != b.id
    assert a.is_guest and a.google_sub.startswith("guest:")
    assert a.profile is not None
