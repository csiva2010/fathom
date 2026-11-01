"""CSRF defence in depth: state-changing requests must come from an allowed origin.

SameSite=Lax cookies already block most cross-site posts; this rejects the rest.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: list[str]):
        self.app = app
        self.allowed = {o.rstrip("/") for o in allowed_origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            origin = dict(scope.get("headers", [])).get(b"origin")
            # Requests without an Origin header (curl, server-to-server, MCP) are allowed;
            # browsers always send one on cross-site requests.
            if origin is not None and origin.decode().rstrip("/") not in self.allowed:
                response = JSONResponse(
                    {
                        "error": {
                            "code": "forbidden_origin",
                            "message": "This request came from an origin that isn't allowed.",
                            "retryable": False,
                        }
                    },
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
