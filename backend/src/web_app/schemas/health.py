from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ProviderHealth(BaseModel):
    name: str
    configured: bool
    circuit: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    env: str
    auth_mode: str
    database: bool
    knowledge_index: bool
    providers: list[ProviderHealth]
