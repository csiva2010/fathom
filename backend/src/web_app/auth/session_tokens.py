"""Signed session JWTs carried in an HttpOnly cookie (AU-02, AU-04)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from src.core.errors import NotAuthenticated

ALGORITHM = "HS256"
ISSUER = "ai-finance-assistant"


@dataclass(frozen=True)
class SessionClaims:
    user_id: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class IssuedToken:
    token: str
    expires_at: datetime
    max_age_seconds: int


class SessionTokenService:
    def __init__(
        self,
        secret: str,
        ttl_hours: int,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if not secret:
            raise ValueError("session secret must not be empty")
        self._secret = secret
        self._ttl = timedelta(hours=ttl_hours)
        self._clock = clock

    def issue(self, user_id: str) -> IssuedToken:
        now = self._clock()
        expires_at = now + self._ttl
        token = jwt.encode(
            {"sub": user_id, "iat": now, "exp": expires_at, "iss": ISSUER},
            self._secret,
            algorithm=ALGORITHM,
        )
        return IssuedToken(token, expires_at, int(self._ttl.total_seconds()))

    def verify(self, token: str) -> SessionClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],
                issuer=ISSUER,
                options={"require": ["sub", "exp", "iat"], "verify_exp": False},
            )
        except jwt.PyJWTError as error:
            raise NotAuthenticated("Your session is invalid. Please sign in again.") from error

        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        # Expiry is checked against our clock (not PyJWT's) so tests can control time.
        if expires_at <= self._clock():
            raise NotAuthenticated("Your session has expired. Please sign in again.")
        return SessionClaims(
            user_id=str(payload["sub"]),
            issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
            expires_at=expires_at,
        )

    def should_refresh(self, claims: SessionClaims) -> bool:
        """Sliding refresh: reissue once less than half the lifetime remains."""
        return claims.expires_at - self._clock() < self._ttl / 2
