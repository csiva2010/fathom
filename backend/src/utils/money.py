"""Money and percentage formatting used in agent explanations and logs."""

from __future__ import annotations


def format_usd(amount: float, *, decimals: int = 2) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.{decimals}f}"


def format_percent(value: float, *, decimals: int = 2, signed: bool = False) -> str:
    """`value` is already a percentage (1.5 means 1.5%)."""
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value:.{decimals}f}%"
