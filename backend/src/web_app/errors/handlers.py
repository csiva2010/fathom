"""Turns every error into the {error: {code, message, retryable}} envelope."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.errors import AppError
from src.core.logging import get_logger

log = get_logger(__name__)


def _envelope(status_code: int, code: str, message: str, retryable: bool = False) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "retryable": retryable}},
    )


async def handle_app_error(_request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, AppError)
    if error.status_code >= 500:
        log.warning("app error", extra={"code": error.code, "detail": error.message})
    return _envelope(error.status_code, error.code, error.message, error.retryable)


async def handle_validation_error(_request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    first = error.errors()[0] if error.errors() else {}
    location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    message = f"{location}: {first.get('msg', 'invalid input')}" if location else "Invalid input."
    return _envelope(422, "validation_failed", message)


async def handle_http_error(_request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    code = "not_found" if error.status_code == 404 else "http_error"
    return _envelope(error.status_code, code, str(error.detail))


async def handle_unexpected(_request: Request, error: Exception) -> JSONResponse:
    log.exception("unhandled error", exc_info=error)
    return _envelope(500, "internal_error", "Something went wrong on our side.", retryable=True)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected)
