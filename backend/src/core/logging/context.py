"""Per-request logging context carried through async code via contextvars."""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
thread_id_var: ContextVar[str | None] = ContextVar("thread_id", default=None)


def current_context() -> dict[str, str]:
    """Return the non-empty context fields for inclusion in a log line."""
    fields = {
        "request_id": request_id_var.get(),
        "user_id": user_id_var.get(),
        "thread_id": thread_id_var.get(),
    }
    return {key: value for key, value in fields.items() if value}
