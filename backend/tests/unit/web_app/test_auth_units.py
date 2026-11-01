from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
from authlib.integrations.starlette_client import OAuthError

from src.core.errors import ConfigurationError, NotAuthenticated
from src.web_app.auth.google_client import AuthlibGoogleClient
from src.web_app.auth.session_tokens import SessionTokenService
from tests.conftest import make_settings


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 30, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


# --- Session tokens ----------------------------------------------------------


def test_issue_and_verify_roundtrip() -> None:
    clock = Clock()
    tokens = SessionTokenService("secret", 12, clock=clock)
    issued = tokens.issue("user-1")
    claims = tokens.verify(issued.token)
    assert claims.user_id == "user-1"
    assert issued.max_age_seconds == 12 * 3600
    assert not tokens.should_refresh(claims)

    clock.now += timedelta(hours=7)
    assert tokens.should_refresh(claims)

    clock.now += timedelta(hours=6)
    with pytest.raises(NotAuthenticated, match="expired"):
        tokens.verify(issued.token)


def test_tampered_or_foreign_tokens_rejected() -> None:
    tokens = SessionTokenService("secret", 12)
    with pytest.raises(NotAuthenticated):
        tokens.verify("not-a-jwt")
    forged = jwt.encode({"sub": "u", "iat": 0, "exp": 9999999999}, "other", algorithm="HS256")
    with pytest.raises(NotAuthenticated):
        tokens.verify(forged)
    with pytest.raises(ValueError):
        SessionTokenService("", 12)


# --- Google client -----------------------------------------------------------


class FakeAuthlibClient:
    def __init__(self, token: dict[str, Any] | Exception) -> None:
        self.token = token
        self.redirect_args: tuple[Any, ...] = ()

    async def authorize_redirect(self, request: Any, redirect_uri: str, **kwargs: Any) -> str:
        self.redirect_args = (redirect_uri, kwargs)
        return "redirect"

    async def authorize_access_token(self, request: Any) -> dict[str, Any]:
        if isinstance(self.token, Exception):
            raise self.token
        return self.token


def google_client(
    tmp_path: Path, token: dict[str, Any] | Exception
) -> tuple[AuthlibGoogleClient, FakeAuthlibClient]:
    settings = make_settings(tmp_path, google_client_id="cid", google_client_secret="csecret")
    client = AuthlibGoogleClient(settings)
    fake = FakeAuthlibClient(token)
    client._oauth.create_client = lambda name: fake  # type: ignore[method-assign]
    return client, fake


async def test_google_redirect_uses_pkce_client(tmp_path: Path) -> None:
    client, fake = google_client(tmp_path, {})
    assert await client.authorize_redirect(None, "http://cb") == "redirect"  # type: ignore[arg-type]
    assert fake.redirect_args[0] == "http://cb"


async def test_google_identity_extracted(tmp_path: Path) -> None:
    claims = {
        "sub": "123",
        "email": "a@b.c",
        "name": "A",
        "picture": "http://p",
        "email_verified": True,
    }
    client, _ = google_client(tmp_path, {"userinfo": claims})
    identity = await client.fetch_identity(None)  # type: ignore[arg-type]
    assert identity.sub == "123"
    assert identity.avatar_url == "http://p"


@pytest.mark.parametrize(
    "token",
    [
        OAuthError(error="invalid_grant"),
        {"userinfo": {"sub": "1"}},
        {"userinfo": {"sub": "1", "email": "a@b.c", "email_verified": False}},
    ],
)
async def test_google_identity_failures(tmp_path: Path, token: Any) -> None:
    client, _ = google_client(tmp_path, token)
    with pytest.raises(NotAuthenticated):
        await client.fetch_identity(None)  # type: ignore[arg-type]


async def test_google_not_configured(tmp_path: Path) -> None:
    client = AuthlibGoogleClient(make_settings(tmp_path))
    with pytest.raises(ConfigurationError):
        await client.authorize_redirect(None, "http://cb")  # type: ignore[arg-type]
