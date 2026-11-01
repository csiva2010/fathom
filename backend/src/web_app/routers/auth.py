"""Sign-in / sign-out routes (AU-01, AU-04, AU-05).

`auth.mode` (env AUTH__MODE) picks the sign-in method: google, guest (Google disabled, a new
isolated account per visitor; covers AS-06) or stub (one fixed dev user).
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from src.core.errors import AppError, NotFound
from src.core.logging import get_logger
from src.data.db.repositories.user_repository import GoogleIdentity, UserRepository
from src.web_app.auth.cookies import clear_session_cookie, set_session_cookie
from src.web_app.container import AppContainer
from src.web_app.dependencies import ContainerDep, DbDep
from src.web_app.schemas.auth import AuthConfigOut

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)


def _signed_in_redirect(container: AppContainer, user_id: str) -> RedirectResponse:
    response = RedirectResponse(container.settings.app.frontend_url, status.HTTP_303_SEE_OTHER)
    set_session_cookie(response, container.settings.auth, container.session_tokens.issue(user_id))
    return response


def _error_redirect(container: AppContainer, code: str) -> RedirectResponse:
    query = urlencode({"auth_error": code})
    return RedirectResponse(
        f"{container.settings.app.frontend_url}/?{query}", status.HTTP_303_SEE_OTHER
    )


@router.get("/config", response_model=AuthConfigOut, summary="Which sign-in options are on")
def auth_config(container: ContainerDep) -> AuthConfigOut:
    mode = container.settings.auth.mode
    return AuthConfigOut(mode=mode, google_enabled=mode != "guest", guest_enabled=mode == "guest")


@router.post("/guest", status_code=status.HTTP_204_NO_CONTENT, summary="Sign in as a new guest")
def guest_login(container: ContainerDep, db: DbDep) -> Response:
    if container.settings.auth.mode != "guest":
        raise NotFound("Guest sign-in is not enabled.")
    user = UserRepository(db).create_guest()
    db.commit()
    log.info("guest signed in", extra={"user_id": user.id})
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookie(response, container.settings.auth, container.session_tokens.issue(user.id))
    return response


@router.get("/google/login", summary="Start Google sign-in (redirect)")
async def google_login(request: Request, container: ContainerDep, db: DbDep) -> Response:
    auth = container.settings.auth
    if auth.mode == "guest":
        return _error_redirect(container, "google_disabled")
    if auth.mode == "stub":
        # Local dev / tests: sign in as the configured stub user without Google.
        stub = auth.stub_user
        user = UserRepository(db).upsert_from_google(
            GoogleIdentity(sub=stub.sub, email=stub.email, name=stub.name)
        )
        db.commit()
        return _signed_in_redirect(container, user.id)

    return await container.google.authorize_redirect(request, auth.google_redirect_uri)


@router.get("/google/callback", summary="Google redirects here after consent")
async def google_callback(request: Request, container: ContainerDep, db: DbDep) -> Response:
    if container.settings.auth.mode == "guest":
        return _error_redirect(container, "google_disabled")
    if denied := request.query_params.get("error"):
        log.info("google sign-in cancelled", extra={"reason": denied})
        return _error_redirect(container, "cancelled")
    try:
        identity = await container.google.fetch_identity(request)
    except AppError as error:
        log.warning("google sign-in failed", extra={"error": error.code, "detail": error.message})
        return _error_redirect(container, "sign_in_failed")

    user = UserRepository(db).upsert_from_google(identity)
    db.commit()
    log.info("user signed in", extra={"user_id": user.id})
    return _signed_in_redirect(container, user.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="End the session")
def logout(request: Request, container: ContainerDep) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, container.settings.auth)
    request.session.clear()
    return response
