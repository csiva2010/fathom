from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class AuthConfigOut(BaseModel):
    """Public sign-in options so the landing page shows the right button."""

    mode: Literal["google", "guest", "stub"]
    google_enabled: bool
    guest_enabled: bool
