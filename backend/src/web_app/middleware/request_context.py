"""Assigns a request id, binds it to the logging context and logs one line per request.

Pure ASGI (not BaseHTTPMiddleware) so it stays safe for SSE streaming later.
"""

from __future__ import annotations

import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.logging import get_logger
from src.core.logging.context import request_id_var

REQUEST_ID_HEADER = "x-request-id"
log = get_logger("http")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers", [])).get(REQUEST_ID_HEADER.encode())
        request_id = incoming.decode()[:64] if incoming else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            state = scope.get("state") or {}
            log.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    **({"user_id": state["user_id"]} if "user_id" in state else {}),
                },
            )
            request_id_var.reset(token)
