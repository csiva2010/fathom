"""Personal access tokens for the MCP server (MCP-03).

A token is shown once when it is created; only its SHA-256 hash is stored. The `fa_pat_`
prefix makes a leaked token easy to recognise in logs and secret scanners.
"""

from __future__ import annotations

import hashlib
import secrets

TOKEN_PREFIX = "fa_pat_"


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def bearer_token(authorization: str | None) -> str | None:
    """The token from an `Authorization: Bearer <token>` header, or None if there isn't one."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()
