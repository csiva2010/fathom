"""Google OAuth 2.0 / OpenID Connect (AU-01).

The backend owns the whole flow (state + PKCE, code exchange, ID-token verification),
so no Google token ever reaches browser JavaScript.
"""

from __future__ import annotations

from typing import Any, Protocol

from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.requests import Request
from starlette.responses import Response

from src.core.config import Settings
from src.core.errors import ConfigurationError, NotAuthenticated
from src.data.db.repositories.user_repository import GoogleIdentity


class GoogleOAuthClient(Protocol):
    async def authorize_redirect(self, request: Request, redirect_uri: str) -> Response: ...

    async def fetch_identity(self, request: Request) -> GoogleIdentity: ...


class AuthlibGoogleClient:
    """Authlib keeps `state`, `nonce` and the PKCE verifier in the signed Starlette session
    and verifies the ID token's signature, audience, issuer and expiry."""

    def __init__(self, settings: Settings):
        self._configured = settings.google_configured
        self._oauth = OAuth()
        self._oauth.register(
            name="google",
            server_metadata_url=settings.auth.google_metadata_url,
            client_id=settings.google_client_id.get_secret_value(),
            client_secret=settings.google_client_secret.get_secret_value(),
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
        )

    def _client(self) -> Any:  # Authlib's client classes are untyped
        if not self._configured:
            raise ConfigurationError(
                "Google sign-in isn't configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
            )
        return self._oauth.create_client("google")

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> Response:
        response: Response = await self._client().authorize_redirect(
            request, redirect_uri, prompt="select_account"
        )
        return response

    async def fetch_identity(self, request: Request) -> GoogleIdentity:
        try:
            token = await self._client().authorize_access_token(request)
        except OAuthError as error:
            raise NotAuthenticated(f"Google sign-in failed: {error.error}") from error

        claims = token.get("userinfo") or {}
        if not claims.get("sub") or not claims.get("email"):
            raise NotAuthenticated("Google did not return an account id and email.")
        if claims.get("email_verified") is False:
            raise NotAuthenticated("Your Google email address is not verified.")
        return GoogleIdentity(
            sub=str(claims["sub"]),
            email=str(claims["email"]),
            name=str(claims.get("name", "")),
            avatar_url=claims.get("picture"),
        )
