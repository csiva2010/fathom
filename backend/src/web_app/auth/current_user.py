"""`current_user` dependency: validates the caller on every request (AU-02).

Browsers authenticate with the session cookie. The MCP server sends a personal access token
as `Authorization: Bearer <token>` instead (MCP-03). Either way the user id comes from
the verified credential, never from the request body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from src.core.errors import Forbidden, NotAuthenticated
from src.core.logging.context import user_id_var
from src.data.db.models import User
from src.data.db.repositories.api_token_repository import ApiTokenRepository
from src.data.db.repositories.user_repository import UserRepository
from src.web_app.auth.api_tokens import bearer_token, hash_token
from src.web_app.auth.cookies import set_session_cookie
from src.web_app.dependencies import ContainerDep, DbDep


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str
    avatar_url: str | None
    is_guest: bool = False
    via_api_token: bool = False


def get_current_user(
    request: Request,
    response: Response,
    container: ContainerDep,
    db: DbDep,
) -> CurrentUser:
    api_token = bearer_token(request.headers.get("authorization"))
    if api_token is not None:
        user = _user_from_api_token(db, api_token)
    else:
        user = _user_from_session(request, response, container, db)

    # Sync dependencies run in a worker thread, so contextvars set here don't reach the
    # request middleware; request.state does.
    request.state.user_id = user.id
    user_id_var.set(user.id)
    return CurrentUser(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        is_guest=user.is_guest,
        via_api_token=api_token is not None,
    )


def _user_from_session(
    request: Request, response: Response, container: ContainerDep, db: Session
) -> User:
    auth = container.settings.auth
    token = request.cookies.get(auth.session_cookie_name)
    if not token:
        raise NotAuthenticated("Please sign in to continue.")

    tokens = container.session_tokens
    claims = tokens.verify(token)
    user = UserRepository(db).get(claims.user_id)
    if user is None:
        raise NotAuthenticated("Your account was not found. Please sign in again.")

    if tokens.should_refresh(claims):
        set_session_cookie(response, auth, tokens.issue(user.id))
    return user


def _user_from_api_token(db: Session, token: str) -> User:
    repo = ApiTokenRepository(db)
    record = repo.find_active(hash_token(token))
    user = UserRepository(db).get(record.user_id) if record else None
    if record is None or user is None:
        raise NotAuthenticated(
            "This access token is invalid or was revoked. Create a new one on the Profile page."
        )
    if repo.mark_used(record):
        db.commit()
    return user


def get_session_user(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    """Like `current_user`, but refuses access tokens: a leaked token can't mint new ones."""
    if user.via_api_token:
        raise Forbidden("Access tokens can only be managed from the app's Profile page.")
    return user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
SessionUserDep = Annotated[CurrentUser, Depends(get_session_user)]
