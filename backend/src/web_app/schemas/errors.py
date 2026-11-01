from __future__ import annotations

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ErrorEnvelope(BaseModel):
    """Every error response uses this shape: {error: {code, message, retryable}}."""

    error: ErrorBody
