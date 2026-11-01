"""Ticker normalisation and format validation (US stocks and ETFs only)."""

from __future__ import annotations

import re

from src.core.errors import ValidationFailed

MAX_SYMBOLS = 50
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9]{0,5}([.\-][A-Z]{1,2})?$")


def normalise_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if not _SYMBOL_RE.match(symbol):
        raise ValidationFailed(f"'{raw.strip()}' doesn't look like a US stock or ETF ticker.")
    return symbol


def normalise_symbols(raw: list[str] | str) -> list[str]:
    items = raw.split(",") if isinstance(raw, str) else raw
    symbols: list[str] = []
    for item in items:
        if item.strip():
            symbol = normalise_symbol(item)
            if symbol not in symbols:
                symbols.append(symbol)
    if not symbols:
        raise ValidationFailed("Provide at least one ticker symbol.")
    if len(symbols) > MAX_SYMBOLS:
        raise ValidationFailed(f"Request at most {MAX_SYMBOLS} symbols at a time.")
    return symbols
