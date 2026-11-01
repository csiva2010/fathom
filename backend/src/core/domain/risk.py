"""Risk profiles shared by portfolio analysis and goal planning (PF-04, GL-01)."""

from __future__ import annotations

from enum import StrEnum


class RiskProfile(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"

    @property
    def rank(self) -> int:
        return list(RiskProfile).index(self)
