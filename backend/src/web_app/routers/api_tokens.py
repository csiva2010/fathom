"""Personal access tokens for the MCP server (MCP-03).

Tokens are created and revoked only from a signed-in browser session; a request that
authenticates with a token can't manage tokens.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from src.data.db.models import ApiToken
from src.data.db.repositories.api_token_repository import ApiTokenRepository
from src.web_app.auth.api_tokens import hash_token, new_token
from src.web_app.auth.current_user import SessionUserDep
from src.web_app.dependencies import DbDep
from src.web_app.schemas.api_tokens import ApiTokenCreated, ApiTokenIn, ApiTokenList, ApiTokenOut

router = APIRouter(prefix="/me/tokens", tags=["tokens"])


def _out(token: ApiToken) -> ApiTokenOut:
    return ApiTokenOut(
        id=token.id,
        name=token.name,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
    )


@router.get("", response_model=ApiTokenList, summary="Your active access tokens")
def list_tokens(user: SessionUserDep, db: DbDep) -> ApiTokenList:
    return ApiTokenList(tokens=[_out(t) for t in ApiTokenRepository(db).list_active(user.id)])


@router.post(
    "",
    response_model=ApiTokenCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create an access token (shown once)",
)
def create_token(body: ApiTokenIn, user: SessionUserDep, db: DbDep) -> ApiTokenCreated:
    secret = new_token()
    token = ApiTokenRepository(db).create(user.id, body.name.strip(), hash_token(secret))
    db.commit()
    return ApiTokenCreated(**_out(token).model_dump(), token=secret)


@router.delete(
    "/{token_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke an access token"
)
def revoke_token(token_id: str, user: SessionUserDep, db: DbDep) -> Response:
    repo = ApiTokenRepository(db)
    repo.revoke(repo.get_owned(user.id, token_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
