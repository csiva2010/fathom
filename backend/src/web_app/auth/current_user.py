"""`current_user` dependency: validates the session cookie on every request (AU-02).

The user id always comes from the verified session, never from the request body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Response

from src.core.errors import NotAuthenticated
from src.core.logging.context import user_id_var
from src.data.db.repositories.user_repository import UserRepository
from src.web_app.auth.cookies import set_session_cookie
from src.web_app.dependencies import ContainerDep, DbDep


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str
    avatar_url: str | None
    is_guest: bool = False


def get_current_user(
    request: Request,
    response: Response,
    container: ContainerDep,
    db: DbDep,
) -> CurrentUser:
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
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
