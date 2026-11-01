"""Parse a holdings CSV (PF-01): symbol, quantity, optional cost basis and asset class.

Headers are matched case-insensitively with common broker-export names ("Shares",
"Qty", "Cost Basis", "Avg Cost"). Bad rows are reported with their line number instead
of failing the whole file, so the user can fix them in the form. Limits: 1 MB, 200 rows.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

MAX_BYTES = 1_000_000
MAX_ROWS = 200
ASSET_CLASSES = ("stock", "etf", "bond_etf", "cash", "other")

_HEADERS: dict[str, tuple[str, ...]] = {
    "symbol": ("symbol", "ticker", "security", "instrument"),
    "quantity": ("quantity", "shares", "qty", "units", "position"),
    "cost_basis": (
        "cost_basis",
        "cost basis",
        "avg cost",
        "average cost",
        "cost per share",
        "price paid",
        "cost",
    ),
    "asset_class": ("asset_class", "asset class", "type", "asset type"),
}
_SYMBOL = re.compile(r"^[A-Z]{1,5}([.-][A-Z]{1,2})?$")


@dataclass(frozen=True)
class ParsedHolding:
    symbol: str
    quantity: float
    cost_basis: float | None = None
    asset_class: str | None = None


@dataclass
class CsvResult:
    holdings: list[ParsedHolding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _number(text: str) -> float | None:
    cleaned = text.strip().replace(",", "").replace("$", "")
    if not cleaned:
        return None
    return float(cleaned)


def _columns(header: list[str]) -> dict[str, int]:
    names = [h.strip().lower().replace("_", " ") for h in header]
    found: dict[str, int] = {}
    for column, aliases in _HEADERS.items():
        for alias in aliases:
            key = alias.replace("_", " ")
            if key in names:
                found[column] = names.index(key)
                break
    return found


def parse_holdings_csv(text: str) -> CsvResult:
    result = CsvResult()
    if len(text.encode("utf-8")) > MAX_BYTES:
        result.errors.append("The file is larger than 1 MB.")
        return result
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        result.errors.append("The file is empty.")
        return result

    columns = _columns(rows[0])
    missing = [c for c in ("symbol", "quantity") if c not in columns]
    if missing:
        result.errors.append(
            "The first row must be a header with symbol and quantity columns "
            f"(missing: {', '.join(missing)})."
        )
        return result
    if len(rows) - 1 > MAX_ROWS:
        result.errors.append(f"Only the first {MAX_ROWS} rows were read.")

    for line, row in enumerate(rows[1 : MAX_ROWS + 1], start=2):

        def cell(column: str, row: list[str] = row) -> str:
            index = columns.get(column)
            return row[index].strip() if index is not None and index < len(row) else ""

        symbol = cell("symbol").upper().lstrip("$")
        if not _SYMBOL.match(symbol):
            result.errors.append(f"Row {line}: '{cell('symbol')}' isn't a valid ticker.")
            continue
        try:
            quantity = _number(cell("quantity"))
            cost = _number(cell("cost_basis"))
        except ValueError:
            result.errors.append(f"Row {line}: quantity and cost basis must be numbers.")
            continue
        if quantity is None or quantity <= 0:
            result.errors.append(f"Row {line}: quantity must be more than 0.")
            continue
        if cost is not None and cost < 0:
            result.errors.append(f"Row {line}: cost basis can't be negative.")
            continue
        asset_class = cell("asset_class").lower().replace(" ", "_") or None
        if asset_class is not None and asset_class not in ASSET_CLASSES:
            asset_class = None  # unknown labels fall back to reference data
        result.holdings.append(ParsedHolding(symbol, quantity, cost, asset_class))
    return result
