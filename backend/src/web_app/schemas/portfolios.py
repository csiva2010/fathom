from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.core.domain.market import AssetClass
from src.utils.holdings_csv import MAX_BYTES, MAX_ROWS


class HoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    quantity: float = Field(gt=0, le=1_000_000_000)
    cost_basis: float | None = Field(default=None, ge=0, le=10_000_000, description="Per share")
    asset_class: AssetClass | None = None


class PortfolioIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    holdings: list[HoldingIn] = Field(min_length=1, max_length=MAX_ROWS)


class HoldingOut(BaseModel):
    symbol: str
    quantity: float
    cost_basis: float | None
    asset_class: AssetClass | None


class PortfolioOut(BaseModel):
    id: str
    name: str
    description: str
    is_sample: bool
    created_at: datetime
    holdings: list[HoldingOut]


class PortfolioList(BaseModel):
    portfolios: list[PortfolioOut]


class CsvImportIn(BaseModel):
    content: str = Field(max_length=MAX_BYTES, description="The CSV file's text")


class CsvImportOut(BaseModel):
    """Parsed rows to review in the form before saving, plus per-row problems."""

    holdings: list[HoldingIn]
    errors: list[str]
