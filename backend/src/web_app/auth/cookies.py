"""Session cookie helpers: HttpOnly, SameSite=Lax, Secure when behind HTTPS."""

from __future__ import annotations

from starlette.responses import Response

from src.core.config.settings import AuthConfig
from src.web_app.auth.session_tokens import IssuedToken


def set_session_cookie(response: Response, auth: AuthConfig, issued: IssuedToken) -> None:
    response.set_cookie(
        key=auth.session_cookie_name,
        value=issued.token,
        max_age=issued.max_age_seconds,
        httponly=True,
        secure=auth.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, auth: AuthConfig) -> None:
    response.delete_cookie(
        key=auth.session_cookie_name,
        httponly=True,
        secure=auth.cookie_secure,
        samesite="lax",
        path="/",
    )
