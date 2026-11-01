"""Ticker normalisation, format validation and symbol search (US stocks and ETFs only)."""

from __future__ import annotations

import difflib
import re
from collections.abc import Sequence

from src.core.domain.market import SymbolInfo
from src.core.errors import ValidationFailed

MAX_SYMBOLS = 50
MAX_QUERY_LENGTH = 50
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


def search_symbols(entries: Sequence[SymbolInfo], query: str, limit: int = 10) -> list[SymbolInfo]:
    """Rank matches: exact ticker, ticker prefix, name word prefix, then name substring (MD-09)."""
    needle = query.strip().upper()
    if not needle:
        return []
    ranked: list[tuple[int, int, str, SymbolInfo]] = []
    for entry in entries:
        name = entry.name.upper()
        if entry.symbol == needle:
            rank = 0
        elif entry.symbol.startswith(needle):
            rank = 1
        elif any(word.startswith(needle) for word in name.split()):
            rank = 2
        elif needle in name:
            rank = 3
        else:
            continue
        ranked.append((rank, len(entry.symbol), entry.symbol, entry))
    ranked.sort(key=lambda item: item[:3])
    return [entry for *_, entry in ranked[:limit]]


def suggest_symbols(known: Sequence[str], symbol: str, limit: int = 3) -> list[str]:
    """Close spellings of an unknown ticker, for a helpful error message."""
    return difflib.get_close_matches(symbol, known, n=limit, cutoff=0.6)
