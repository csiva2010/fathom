"""Loads the static seed files that back the mock provider and reference-data fallback."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.core.domain.market import ReferenceData


@lru_cache(maxsize=4)
def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class SeedData:
    def __init__(self, seed_dir: Path):
        self.seed_dir = seed_dir

    @property
    def base_prices(self) -> dict[str, float]:
        data: dict[str, float] = _read_json(str(self.seed_dir / "mock_prices.json"))
        return data

    @property
    def reference(self) -> dict[str, ReferenceData]:
        raw: dict[str, dict[str, Any]] = _read_json(str(self.seed_dir / "reference_data.json"))
        return {symbol: ReferenceData(symbol=symbol, **fields) for symbol, fields in raw.items()}

    @property
    def sample_portfolios(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = _read_json(str(self.seed_dir / "sample_portfolios.json"))
        return data
