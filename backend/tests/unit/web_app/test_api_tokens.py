"""Personal access tokens: generation, hashing, header parsing and the repository (MCP-03)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from src.core.errors import NotFound, ValidationFailed
from src.data.db.repositories.api_token_repository import MAX_ACTIVE_TOKENS, ApiTokenRepository
from src.data.db.repositories.user_repository import GoogleIdentity, UserRepository
from src.web_app.auth.api_tokens import TOKEN_PREFIX, bearer_token, hash_token, new_token


def test_tokens_are_prefixed_unique_and_hashed() -> None:
    first, second = new_token(), new_token()
    assert first.startswith(TOKEN_PREFIX) and first != second and len(first) > 40
    assert hash_token(first) == hash_token(first) != hash_token(second)
    assert len(hash_token(first)) == 64 and first not in hash_token(first)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer fa_pat_abc", "fa_pat_abc"),
        ("bearer   fa_pat_abc ", "fa_pat_abc"),
        ("Basic dXNlcjpwYXNz", None),
        ("Bearer ", None),
        ("", None),
        (None, None),
    ],
)
def test_bearer_token_parsing(header: str | None, expected: str | None) -> None:
    assert bearer_token(header) == expected


def make_user(db: Session, sub: str = "g-tokens") -> str:
    return UserRepository(db).upsert_from_google(GoogleIdentity(sub=sub, email="t@x.com")).id


def test_create_list_revoke_and_find(db: Session) -> None:
    repo = ApiTokenRepository(db)
    owner, other = make_user(db), make_user(db, "g-other")
    first = repo.create(owner, "Laptop", hash_token("one"))
    second = repo.create(owner, "Desktop", hash_token("two"))

    assert {t.id for t in repo.list_active(owner)} == {first.id, second.id}
    assert repo.list_active(other) == []
    assert repo.find_active(hash_token("one")) is first
    assert repo.find_active(hash_token("nope")) is None

    # Scoped by owner: another user can't see or revoke it.
    with pytest.raises(NotFound):
        repo.get_owned(other, first.id)
    repo.revoke(repo.get_owned(owner, first.id))
    assert first.revoked_at is not None
    assert repo.find_active(hash_token("one")) is None
    assert [t.id for t in repo.list_active(owner)] == [second.id]
    with pytest.raises(NotFound):
        repo.get_owned(owner, first.id)  # already revoked


def test_active_token_limit(db: Session) -> None:
    repo = ApiTokenRepository(db)
    owner = make_user(db)
    for n in range(MAX_ACTIVE_TOKENS):
        repo.create(owner, f"t{n}", hash_token(f"t{n}"))
    with pytest.raises(ValidationFailed, match="up to 10 active tokens"):
        repo.create(owner, "one too many", hash_token("extra"))


def test_mark_used_writes_at_most_once_a_minute(db: Session) -> None:
    repo = ApiTokenRepository(db)
    token = repo.create(make_user(db), "Laptop", hash_token("one"))
    now = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

    assert repo.mark_used(token, now) is True and token.last_used_at == now
    assert repo.mark_used(token, now + timedelta(seconds=30)) is False
    # SQLite hands back naive datetimes; they are treated as UTC.
    token.last_used_at = now.replace(tzinfo=None)
    assert repo.mark_used(token, now + timedelta(seconds=30)) is False
    assert repo.mark_used(token, now + timedelta(minutes=2)) is True
