"""Personal access tokens (MCP-03). Every lookup except `find_active` is scoped by user id."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.errors import NotFound, ValidationFailed
from src.data.db.base import utcnow
from src.data.db.models import ApiToken

MAX_ACTIVE_TOKENS = 10
# Recording every use would write to the DB on each MCP call; once a minute is enough.
LAST_USED_RESOLUTION = timedelta(minutes=1)


class ApiTokenRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_active(self, user_id: str) -> list[ApiToken]:
        stmt = (
            select(ApiToken)
            .where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
            .order_by(ApiToken.created_at.desc())
        )
        return list(self._session.scalars(stmt))

    def create(self, user_id: str, name: str, token_hash: str) -> ApiToken:
        if len(self.list_active(user_id)) >= MAX_ACTIVE_TOKENS:
            raise ValidationFailed(
                f"You can have up to {MAX_ACTIVE_TOKENS} active tokens. Revoke one first."
            )
        token = ApiToken(user_id=user_id, name=name, token_hash=token_hash)
        self._session.add(token)
        self._session.flush()
        return token

    def get_owned(self, user_id: str, token_id: str) -> ApiToken:
        token = self._session.get(ApiToken, token_id)
        if token is None or token.user_id != user_id or token.revoked_at is not None:
            raise NotFound("That token doesn't exist or was already revoked.")
        return token

    def revoke(self, token: ApiToken) -> None:
        token.revoked_at = utcnow()
        self._session.flush()

    def find_active(self, token_hash: str) -> ApiToken | None:
        return self._session.scalar(
            select(ApiToken).where(ApiToken.token_hash == token_hash, ApiToken.revoked_at.is_(None))
        )

    def mark_used(self, token: ApiToken, now: datetime | None = None) -> bool:
        """Record a use; returns True when the row changed and needs a commit."""
        now = now or utcnow()
        last = token.last_used_at
        # SQLite returns naive datetimes; they are stored in UTC.
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=now.tzinfo)
        if last is not None and now - last < LAST_USED_RESOLUTION:
            return False
        token.last_used_at = now
        self._session.flush()
        return True
