from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApiTokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="A label, e.g. 'Claude Desktop'")


class ApiTokenOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    last_used_at: datetime | None


class ApiTokenCreated(ApiTokenOut):
    """The only response that carries the token itself; it can't be shown again."""

    token: str


class ApiTokenList(BaseModel):
    tokens: list[ApiTokenOut]
