"""Portfolio analytics as pure functions (PF-02 to PF-06).

Inputs are holdings, prices, reference data and price bars that the caller already fetched;
nothing here does I/O. Weights and expense ratios are fractions, `_percent` values are
percentages.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from src.core.domain.market import AssetClass, Bar, ReferenceData
from src.core.domain.portfolio import (
    AllocationSlice,
    BenchmarkComparison,
    Diversification,
    HoldingInput,
    HoldingMetrics,
    Observation,
    PortfolioAnalysis,
    ProfileFit,
    RiskMetrics,
)
from src.core.domain.risk import RiskProfile
from src.core.services.indicators import annualized_volatility, max_drawdown, percent_change
from src.utils.money import format_percent

FUND_CLASSES = frozenset({AssetClass.ETF, AssetClass.BOND_ETF})

# Diversification score (PF-03). A fund already holds many companies, so for concentration
# purposes it counts like this many equal positions.
FUND_EQUIVALENT_POSITIONS = 20
TARGET_EFFECTIVE_HOLDINGS = 20  # at or above this, the holdings half of the score is full
TARGET_EFFECTIVE_SECTORS = 8  # at or above this, the sector half of the score is full

# Educational volatility bands used to describe a portfolio's risk level (PF-04).
CONSERVATIVE_MAX_VOLATILITY = 10.0
MODERATE_MAX_VOLATILITY = 16.0

# Thresholds that trigger a learning point (PF-06).
SINGLE_POSITION_WEIGHT = 0.20
SECTOR_WEIGHT = 0.40
HIGH_EXPENSE_RATIO = 0.005
LOW_DIVERSIFICATION_SCORE = 40

UNCLASSIFIED = "Unclassified"
FIXED_INCOME = "Fixed Income"


# --- Holdings and value (PF-02) -----------------------------------------------


def merge_holdings(holdings: Iterable[HoldingInput]) -> list[HoldingInput]:
    """Combine repeated symbols; the merged cost basis is quantity-weighted.

    A merged cost basis is kept only when every lot has one. Zero-quantity lots are dropped.
    """
    grouped: dict[str, list[HoldingInput]] = defaultdict(list)
    for holding in holdings:
        if holding.quantity > 0:
            grouped[holding.symbol].append(holding)

    merged: list[HoldingInput] = []
    for symbol, lots in grouped.items():
        quantity = sum(lot.quantity for lot in lots)
        has_cost = all(lot.cost_basis is not None for lot in lots)
        cost = sum(lot.quantity * (lot.cost_basis or 0) for lot in lots) if has_cost else None
        merged.append(
            HoldingInput(
                symbol=symbol,
                quantity=quantity,
                cost_basis=cost / quantity if cost is not None else None,
                asset_class=next((lot.asset_class for lot in lots if lot.asset_class), None),
            )
        )
    return merged


def value_holdings(
    holdings: Sequence[HoldingInput],
    prices: Mapping[str, float],
    reference: Mapping[str, ReferenceData],
) -> list[HoldingMetrics]:
    """Market value, gain/loss and weight per priced holding, largest first.

    Holdings without a price are left out; the caller reports them as unpriced.
    """
    priced = [h for h in holdings if h.symbol in prices and h.quantity > 0]
    values = {h.symbol: h.quantity * prices[h.symbol] for h in priced}
    total = sum(values.values())

    metrics: list[HoldingMetrics] = []
    for holding in priced:
        ref = reference.get(holding.symbol) or ReferenceData(symbol=holding.symbol)
        asset_class = holding.asset_class or ref.asset_class
        value = values[holding.symbol]
        cost = holding.quantity * holding.cost_basis if holding.cost_basis is not None else None
        gain = value - cost if cost is not None else None
        metrics.append(
            HoldingMetrics(
                symbol=holding.symbol,
                name=ref.name,
                asset_class=asset_class,
                quantity=holding.quantity,
                price=prices[holding.symbol],
                market_value=round(value, 2),
                cost_value=round(cost, 2) if cost is not None else None,
                gain=round(gain, 2) if gain is not None else None,
                gain_percent=_round(percent_change(cost, value) if cost else None),
                weight=value / total if total else 0.0,
                sector=ref.sector if asset_class not in FUND_CLASSES else None,
                beta=ref.beta,
                expense_ratio=ref.expense_ratio if asset_class in FUND_CLASSES else None,
            )
        )
    metrics.sort(key=lambda m: m.market_value, reverse=True)
    return metrics


def _slices(values: Mapping[str, float]) -> list[AllocationSlice]:
    total = sum(values.values())
    slices = [
        AllocationSlice(label=label, value=round(value, 2), weight=value / total if total else 0)
        for label, value in values.items()
        if value > 0
    ]
    return sorted(slices, key=lambda s: s.value, reverse=True)


def allocation_by_holding(metrics: Sequence[HoldingMetrics]) -> list[AllocationSlice]:
    return _slices({m.symbol: m.market_value for m in metrics})


def allocation_by_asset_class(metrics: Sequence[HoldingMetrics]) -> list[AllocationSlice]:
    values: dict[str, float] = defaultdict(float)
    for m in metrics:
        values[m.asset_class.value] += m.market_value
    return _slices(values)


def allocation_by_sector(
    metrics: Sequence[HoldingMetrics], reference: Mapping[str, ReferenceData]
) -> list[AllocationSlice]:
    """Sector exposure, looking through funds with known sector weights."""
    values: dict[str, float] = defaultdict(float)
    for m in metrics:
        ref = reference.get(m.symbol)
        weights = ref.sector_weights if ref else []
        if m.asset_class in FUND_CLASSES and weights:
            covered = 0.0
            for sector_weight in weights:
                values[sector_weight.sector] += m.market_value * sector_weight.weight
                covered += sector_weight.weight
            if covered < 1:
                values["Other"] += m.market_value * (1 - covered)
        elif m.asset_class is AssetClass.BOND_ETF:
            values[FIXED_INCOME] += m.market_value
        elif m.asset_class is AssetClass.CASH:
            values["Cash"] += m.market_value
        else:
            values[m.sector or UNCLASSIFIED] += m.market_value
    return _slices(values)


def weighted_expense_ratio(metrics: Sequence[HoldingMetrics]) -> float | None:
    """Yearly fund fees as a fraction of the whole portfolio; single stocks cost 0.

    None when the portfolio is empty or holds a fund whose fee is unknown.
    """
    total = sum(m.market_value for m in metrics)
    if not total:
        return None
    if any(m.asset_class in FUND_CLASSES and m.expense_ratio is None for m in metrics):
        return None
    return sum(m.market_value * (m.expense_ratio or 0) for m in metrics) / total


# --- Diversification (PF-03) --------------------------------------------------


def herfindahl(weights: Iterable[float]) -> float:
    """Sum of squared weights: 1 means everything in one place."""
    return sum(w * w for w in weights)


def _component(effective: float, target: int) -> float:
    return min(1.0, max(0.0, (effective - 1) / (target - 1)))


def diversification(
    metrics: Sequence[HoldingMetrics], sectors: Sequence[AllocationSlice]
) -> Diversification:
    """Half from how spread the positions are (funds count as broad baskets), half from
    how spread the sector exposure is."""
    if not metrics:
        return Diversification(score=0, effective_holdings=0, effective_sectors=0)

    holding_hhi = sum(
        m.weight**2 / (FUND_EQUIVALENT_POSITIONS if m.asset_class in FUND_CLASSES else 1)
        for m in metrics
    )
    sector_hhi = herfindahl(s.weight for s in sectors)
    effective_holdings = 1 / holding_hhi if holding_hhi else 0.0
    effective_sectors = 1 / sector_hhi if sector_hhi else 0.0
    score = round(
        100
        * (
            0.5 * _component(effective_holdings, TARGET_EFFECTIVE_HOLDINGS)
            + 0.5 * _component(effective_sectors, TARGET_EFFECTIVE_SECTORS)
        )
    )

    largest = max(metrics, key=lambda m: m.weight)
    top_sector = sectors[0] if sectors else None
    drivers = [
        f"Largest position: {largest.symbol} at {_pct(largest.weight)} of the portfolio.",
        f"The positions spread risk about as much as {effective_holdings:.0f} equal holdings "
        f"(each fund counts as {FUND_EQUIVALENT_POSITIONS}, since it holds many companies).",
    ]
    if top_sector is not None:
        drivers.append(
            f"Largest sector exposure: {top_sector.label} at {_pct(top_sector.weight)}, "
            f"about as spread as {effective_sectors:.1f} equal sectors."
        )
    return Diversification(
        score=score,
        effective_holdings=round(effective_holdings, 1),
        effective_sectors=round(effective_sectors, 1),
        largest_holding=largest.symbol,
        largest_holding_weight=largest.weight,
        largest_sector=top_sector.label if top_sector else None,
        largest_sector_weight=top_sector.weight if top_sector else 0.0,
        drivers=drivers,
    )


# --- Risk (PF-04) and benchmark (PF-05) ---------------------------------------


def weighted_beta(metrics: Sequence[HoldingMetrics]) -> tuple[float | None, float]:
    """Value-weighted beta over holdings with a known beta, and the share of value covered."""
    known = [m for m in metrics if m.beta is not None]
    covered = sum(m.weight for m in known)
    if not known or covered == 0:
        return None, 0.0
    return sum(m.weight * (m.beta or 0) for m in known) / covered, covered


def value_series(
    quantities: Mapping[str, float], bars_by_symbol: Mapping[str, Sequence[Bar]]
) -> list[tuple[date, float]]:
    """Daily value of today's holdings replayed over history, on dates every symbol traded.

    Symbols with no bars are left out of the series.
    """
    closes: dict[str, dict[date, float]] = {
        symbol: {bar.t.date(): bar.close for bar in bars}
        for symbol, bars in bars_by_symbol.items()
        if bars and symbol in quantities
    }
    if not closes:
        return []
    common = set.intersection(*(set(by_day) for by_day in closes.values()))
    return [
        (day, sum(quantities[symbol] * by_day[day] for symbol, by_day in closes.items()))
        for day in sorted(common)
    ]


def classify_volatility(volatility_percent: float) -> RiskProfile:
    if volatility_percent <= CONSERVATIVE_MAX_VOLATILITY:
        return RiskProfile.CONSERVATIVE
    if volatility_percent <= MODERATE_MAX_VOLATILITY:
        return RiskProfile.MODERATE
    return RiskProfile.AGGRESSIVE


def profile_fit(level: RiskProfile, profile: RiskProfile) -> ProfileFit:
    if level.rank > profile.rank:
        return ProfileFit.ABOVE
    if level.rank < profile.rank:
        return ProfileFit.BELOW
    return ProfileFit.WITHIN


def risk_metrics(
    metrics: Sequence[HoldingMetrics],
    series: Sequence[tuple[date, float]],
    profile: RiskProfile | None = None,
) -> RiskMetrics:
    beta, coverage = weighted_beta(metrics)
    values = [value for _, value in series]
    volatility = annualized_volatility(values, window=None)
    level = classify_volatility(volatility) if volatility is not None else None
    return RiskMetrics(
        weighted_beta=_round(beta),
        beta_coverage=round(coverage, 4),
        annualized_volatility_percent=_round(volatility),
        max_drawdown_percent=_round(max_drawdown(values)) if len(values) > 1 else None,
        history_days=len(values),
        risk_level=level,
        profile=profile,
        profile_fit=profile_fit(level, profile) if level and profile else None,
    )


def compare_to_benchmark(
    series: Sequence[tuple[date, float]],
    benchmark_bars: Sequence[Bar],
    benchmark_symbol: str,
    range_label: str,
) -> BenchmarkComparison | None:
    """Both returns measured over the dates the portfolio and benchmark share."""
    benchmark = {bar.t.date(): bar.close for bar in benchmark_bars}
    aligned = [(day, value, benchmark[day]) for day, value in series if day in benchmark]
    if len(aligned) < 2:
        return None
    (start, p0, b0), (end, p1, b1) = aligned[0], aligned[-1]
    portfolio_return = percent_change(p0, p1)
    benchmark_return = percent_change(b0, b1)
    if portfolio_return is None or benchmark_return is None:
        return None
    return BenchmarkComparison(
        benchmark_symbol=benchmark_symbol,
        range=range_label,
        start=start,
        end=end,
        portfolio_return_percent=round(portfolio_return, 2),
        benchmark_return_percent=round(benchmark_return, 2),
        difference_percent=round(portfolio_return - benchmark_return, 2),
    )


# --- Educational observations (PF-06) -----------------------------------------


def observations(
    metrics: Sequence[HoldingMetrics],
    sectors: Sequence[AllocationSlice],
    diversification_result: Diversification,
    risk: RiskMetrics,
    unpriced: Sequence[str] = (),
) -> list[Observation]:
    """Learning points phrased as explanations, never as buy/sell/hold instructions."""
    notes: list[Observation] = []

    for m in metrics:
        if m.asset_class not in FUND_CLASSES and m.weight > SINGLE_POSITION_WEIGHT:
            notes.append(
                Observation(
                    code="single_position",
                    message=(
                        f"{m.symbol} is {_pct(m.weight)} of this portfolio. When one company is "
                        "this large a share, its results drive much of the portfolio's ups "
                        "and downs."
                    ),
                )
            )

    for s in sectors:
        if s.label not in ("Other", UNCLASSIFIED, FIXED_INCOME) and s.weight > SECTOR_WEIGHT:
            notes.append(
                Observation(
                    code="sector_concentration",
                    message=(
                        f"About {_pct(s.weight)} of the money is exposed to {s.label}, counting "
                        "what the funds hold. Companies in one sector often move together, so "
                        "a sector-wide slump would hit most of the portfolio at once."
                    ),
                )
            )

    for m in metrics:
        if m.expense_ratio is not None and m.expense_ratio > HIGH_EXPENSE_RATIO:
            notes.append(
                Observation(
                    code="high_fee_fund",
                    message=(
                        f"{m.symbol} charges a {_pct(m.expense_ratio, 2)} yearly expense ratio. "
                        "Fees are taken every year whatever the fund returns, and over long "
                        "periods they compound into a noticeable drag."
                    ),
                )
            )

    if metrics and not any(
        m.asset_class in (AssetClass.BOND_ETF, AssetClass.CASH) for m in metrics
    ):
        notes.append(
            Observation(
                code="all_equity",
                message=(
                    "Everything here is in stocks or stock funds. Bonds and cash usually swing "
                    "less than stocks, which is why mixes for lower risk levels include them."
                ),
            )
        )

    if metrics and diversification_result.score < LOW_DIVERSIFICATION_SCORE:
        notes.append(
            Observation(
                code="low_diversification",
                message=(
                    f"The diversification score is {diversification_result.score} out of 100, "
                    "mostly because the money is concentrated in a few positions or sectors."
                ),
            )
        )

    if risk.profile_fit is ProfileFit.ABOVE and risk.risk_level and risk.profile:
        notes.append(
            Observation(
                code="risk_above_profile",
                message=(
                    f"This portfolio's past swings look like a {risk.risk_level.value} mix, "
                    f"which is more than a {risk.profile.value} profile usually expects."
                ),
            )
        )
    elif risk.profile_fit is ProfileFit.BELOW and risk.risk_level and risk.profile:
        notes.append(
            Observation(
                code="risk_below_profile",
                message=(
                    f"This portfolio's past swings look like a {risk.risk_level.value} mix, "
                    f"calmer than a {risk.profile.value} profile usually expects."
                ),
            )
        )

    if unpriced:
        verb = "it is" if len(unpriced) == 1 else "they are"
        notes.append(
            Observation(
                code="unpriced_symbols",
                message=(
                    f"We couldn't find a price for {', '.join(unpriced)}, so {verb} left out "
                    "of these numbers."
                ),
            )
        )
    return notes


# --- Everything together ----------------------------------------------------


def analyze(
    holdings: Sequence[HoldingInput],
    prices: Mapping[str, float],
    reference: Mapping[str, ReferenceData],
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    risk_profile: RiskProfile | None = None,
    benchmark_bars: Sequence[Bar] = (),
    benchmark_symbol: str = "SPY",
    range_label: str = "1Y",
) -> PortfolioAnalysis:
    merged = merge_holdings(holdings)
    unpriced = [h.symbol for h in merged if h.symbol not in prices]
    metrics = value_holdings(merged, prices, reference)
    sectors = allocation_by_sector(metrics, reference)
    series = value_series({m.symbol: m.quantity for m in metrics}, bars_by_symbol)
    diversification_result = diversification(metrics, sectors)
    risk = risk_metrics(metrics, series, risk_profile)

    total_value = sum(m.market_value for m in metrics)
    costed = [m for m in metrics if m.cost_value is not None]
    total_cost = sum(m.cost_value or 0 for m in costed) if costed else None
    costed_value = sum(m.market_value for m in costed)
    total_gain = costed_value - total_cost if total_cost is not None else None

    return PortfolioAnalysis(
        total_value=round(total_value, 2),
        total_cost=_round(total_cost),
        total_gain=_round(total_gain),
        total_gain_percent=_round(percent_change(total_cost, costed_value) if total_cost else None),
        holdings=metrics,
        allocation_by_holding=allocation_by_holding(metrics),
        allocation_by_asset_class=allocation_by_asset_class(metrics),
        allocation_by_sector=sectors,
        weighted_expense_ratio=weighted_expense_ratio(metrics),
        diversification=diversification_result,
        risk=risk,
        benchmark=compare_to_benchmark(series, benchmark_bars, benchmark_symbol, range_label),
        observations=observations(metrics, sectors, diversification_result, risk, unpriced),
        unpriced=unpriced,
    )


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _pct(fraction: float, decimals: int = 0) -> str:
    return format_percent(fraction * 100, decimals=decimals)
