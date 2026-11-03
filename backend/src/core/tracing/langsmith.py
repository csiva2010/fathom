"""Optional LangSmith tracing of every LangGraph run, LLM call and tool call.

LangChain reads LangSmith settings from the process environment only, while ours come from
`.env` through `Settings`, so they are copied across once at startup. Off unless both
LANGSMITH_TRACING=true and LANGSMITH_API_KEY are set.
"""

from __future__ import annotations

import os

from src.core.config import Settings


def configure_langsmith(settings: Settings, project_suffix: str = "") -> str | None:
    """Turn LangSmith tracing on when configured; return the project name, or None if off."""
    key = settings.langsmith_api_key.get_secret_value()
    if not (settings.langsmith_tracing and key):
        return None
    project = f"{settings.langsmith_project}{project_suffix}"
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ["LANGSMITH_PROJECT"] = project
    if settings.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    return project
