"""Pure functions that turn Alpha Vantage JSON into domain models.

Alpha Vantage answers HTTP 200 even for errors, so the payload itself has to be checked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.core.domain.market import AssetClass, IndexQuote, ReferenceData, SectorWeight
from src.core.errors import ProviderAuthError, ProviderBadResponse, ProviderRateLimited

PROVIDER = "alpha_vantage"


def check_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProviderBadResponse(PROVIDER, "unexpected response shape")
    if "Error Message" in payload:
        raise ProviderBadResponse(PROVIDER, str(payload["Error Message"])[:200])
    notice = str(payload.get("Note") or payload.get("Information") or "")
    if notice:
        lowered = notice.lower()
        if "api key" in lowered and ("invalid" in lowered or "missing" in lowered):
            raise ProviderAuthError(PROVIDER, "API key rejected")
        raise ProviderRateLimited(PROVIDER, "quota or rate limit notice returned")
    return payload


def _to_float(raw: Any) -> float | None:
    if raw in (None, "", "None", "-"):
        return None
    try:
        return float(str(raw).rstrip("%"))
    except ValueError:
        return None


def parse_global_quote(index_id: str, name: str, symbol: str, payload: Any) -> IndexQuote:
    data = check_payload(payload).get("Global Quote") or {}
    price = _to_float(data.get("05. price"))
    if price is None:
        raise ProviderBadResponse(PROVIDER, f"no quote returned for {symbol}")
    trading_day = data.get("07. latest trading day")
    as_of = (
        datetime.fromisoformat(trading_day).replace(tzinfo=UTC)
        if trading_day
        else datetime.now(UTC)
    )
    return IndexQuote(
        id=index_id,
        name=name,
        symbol=symbol,
        is_proxy=False,
        price=price,
        change=_to_float(data.get("09. change")),
        change_percent=_to_float(data.get("10. change percent")),
        as_of=as_of,
    )


def parse_company_overview(symbol: str, payload: Any) -> ReferenceData | None:
    data = check_payload(payload)
    if not data.get("Symbol"):
        return None  # Alpha Vantage returns {} for ETFs and unknown symbols.
    return ReferenceData(
        symbol=symbol,
        name=data.get("Name", ""),
        asset_class=AssetClass.STOCK,
        sector=(data.get("Sector") or None),
        industry=(data.get("Industry") or None),
        beta=_to_float(data.get("Beta")),
    )


def parse_etf_profile(symbol: str, payload: Any) -> ReferenceData | None:
    data = check_payload(payload)
    if not data or ("net_expense_ratio" not in data and "sectors" not in data):
        return None
    sectors = [
        SectorWeight(sector=s.get("sector", "").title(), weight=w)
        for s in data.get("sectors", [])
        if (w := _to_float(s.get("weight"))) is not None
    ]
    return ReferenceData(
        symbol=symbol,
        asset_class=AssetClass.ETF,
        expense_ratio=_to_float(data.get("net_expense_ratio")),
        sector_weights=sectors,
    )
