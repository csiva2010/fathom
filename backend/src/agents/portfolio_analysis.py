"""Portfolio Analysis agent (AG-02, PF-02 to PF-07): explains the user's holdings.

Every metric comes from `PortfolioAnalysisService`, the same service behind the Portfolio
view, so chat and screen show the same numbers. Holdings read from a screenshot in this
conversation (CH-09) are analyzed up front, otherwise the saved portfolio; holdings typed
into the chat can be analyzed with a tool. Screenshot prices are shown for comparison only:
values use live market data. The LLM only explains the
results and the educational observations; it never suggests trades.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from src.agents.base_agent import AgentRun, AgentTool, BaseAgent, Prepared, as_data, to_json
from src.core.domain.market import PriceRange
from src.core.domain.portfolio import HoldingInput, PortfolioAnalysis
from src.core.llm import LLMGateway
from src.core.services.market.market_data_service import MarketDataService
from src.core.services.portfolio_service import PortfolioAnalysisService
from src.utils.money import format_percent, format_usd
from src.workflow.state import AgentName, AgentOutput, Artifact, FinanceState, ScreenshotRead

MAX_CHAT_HOLDINGS = 25

NO_PORTFOLIO_ANSWER = (
    "You don't have a saved portfolio yet, so there's nothing for me to analyze. Add your "
    'holdings in the Portfolio tab, or list them here (for example "10 shares of VTI and '
    "5 of AAPL\") and I'll walk you through the numbers."
)
NO_PORTFOLIO_CONTEXT = (
    "The user has no saved portfolio. If the question lists holdings (symbols and share "
    "counts), call analyze_holdings with them. Otherwise explain briefly that they can add "
    "holdings in the Portfolio tab or list them in the chat, and answer any general part "
    "of the question."
)

SCREENSHOT_NAME = "Your screenshot"
SCREENSHOT_UNREADABLE_ANSWER = (
    "I couldn't find any holdings in that image. Try a screenshot that shows each "
    "position's ticker and share count, or type them here (for example \"10 shares of VTI "
    'and 5 of AAPL").'
)
SCREENSHOT_UNAVAILABLE_ANSWER = (
    "I can't read images right now, so I couldn't analyze that screenshot. Please try "
    'again in a moment, or type your holdings here (for example "10 shares of VTI").'
)


class ChatHolding(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    quantity: float = Field(gt=0, description="Number of shares")


class AnalyzeHoldingsArgs(BaseModel):
    holdings: list[ChatHolding] = Field(min_length=1, max_length=MAX_CHAT_HOLDINGS)


class BenchmarkArgs(BaseModel):
    range: PriceRange = Field(description="Comparison window: 1M, 3M, 6M, 1Y or 5Y")


class SymbolArgs(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)


def _pct(fraction: float | None, decimals: int = 1) -> float | None:
    """A fraction as a rounded percentage for the prompt (0.253 -> 25.3)."""
    return None if fraction is None else round(fraction * 100, decimals)


def analysis_facts(analysis: PortfolioAnalysis) -> dict[str, Any]:
    """The analysis in compact form for the prompt; weights are percentages."""
    risk = analysis.risk
    return {
        "total_value": analysis.total_value,
        "total_gain": analysis.total_gain,
        "total_gain_percent": analysis.total_gain_percent,
        "holdings": [
            {
                "symbol": h.symbol,
                "name": h.name,
                "asset_class": h.asset_class.value,
                "weight_percent": _pct(h.weight),
                "gain_percent": h.gain_percent,
                "expense_ratio_percent": _pct(h.expense_ratio, 2),
            }
            for h in analysis.holdings
        ],
        "asset_classes": [
            {"label": s.label, "percent": _pct(s.weight)}
            for s in analysis.allocation_by_asset_class
        ],
        "top_sectors": [
            {"label": s.label, "percent": _pct(s.weight)} for s in analysis.allocation_by_sector[:5]
        ],
        "weighted_expense_ratio_percent": _pct(analysis.weighted_expense_ratio, 3),
        "diversification": {
            "score_out_of_100": analysis.diversification.score,
            "drivers": analysis.diversification.drivers,
        },
        "risk": {
            "weighted_beta": risk.weighted_beta,
            "annualized_volatility_percent": risk.annualized_volatility_percent,
            "max_drawdown_percent": risk.max_drawdown_percent,
            "behaves_like": risk.risk_level.value if risk.risk_level else None,
            "user_risk_profile": risk.profile.value if risk.profile else None,
            "fit_with_profile": risk.profile_fit.value if risk.profile_fit else None,
        },
        "benchmark": analysis.benchmark.model_dump(mode="json") if analysis.benchmark else None,
        "learning_points": [o.message for o in analysis.observations],
        "unpriced_symbols": analysis.unpriced,
        "data_status": sorted({f.status.value for f in analysis.freshness}),
    }


class PortfolioAnalysisAgent(BaseAgent):
    name = AgentName.PORTFOLIO
    role_prompt = """You are the Portfolio Analysis agent. You explain what the numbers say \
about a user's holdings: value and gains, allocation, diversification, risk, fees and how \
it compared with the benchmark.
- Use only the figures in the portfolio analysis and tool results. Mention when the data is \
cached or mock (data_status) rather than live.
- Explain what each metric means and why it matters, and walk through the learning points.
- Never tell the user to buy, sell, add, trim or rebalance anything, and never propose a \
target allocation for them. Describe trade-offs instead.
- When the holdings came from a screenshot, say so, and note that values use current \
market prices rather than the prices in the image.
- Call tools only for data you don't already have."""

    def __init__(
        self,
        gateway: LLMGateway,
        portfolios: PortfolioAnalysisService,
        market: MarketDataService,
        **kwargs: int,
    ):
        super().__init__(gateway, **kwargs)
        self._portfolios = portfolios
        self._market = market

    def tools(self) -> Sequence[AgentTool]:
        return (
            AgentTool(
                "analyze_holdings",
                "Analyze holdings the user listed in the chat (symbol and share count).",
                AnalyzeHoldingsArgs,
                self._analyze_tool,
            ),
            AgentTool(
                "compare_to_benchmark",
                "Compare the analyzed portfolio with the S&P 500 benchmark over another window.",
                BenchmarkArgs,
                self._benchmark_tool,
            ),
            AgentTool(
                "get_holding_details",
                "Name, asset class, sector, beta and expense ratio for one ticker.",
                SymbolArgs,
                self._details_tool,
            ),
        )

    # --- Prefetch ------------------------------------------------------------

    async def prepare(self, state: FinanceState, run: AgentRun) -> Prepared:
        user = state.get("user")
        risk_profile = user.risk_profile if user else None
        shot = state.get("screenshot")
        if shot is not None and shot.turn_id == state.get("turn_id") and not shot.holdings:
            unavailable = shot.status == "unavailable"
            return Prepared(
                early=AgentOutput(
                    agent=self.name,
                    answer_md=(
                        SCREENSHOT_UNAVAILABLE_ANSWER
                        if unavailable
                        else SCREENSHOT_UNREADABLE_ANSWER
                    ),
                    confidence=0.3,
                    follow_ups=["What makes a portfolio diversified?"],
                )
            )
        if shot is not None and shot.holdings:
            holdings = [HoldingInput(symbol=h.symbol, quantity=h.quantity) for h in shot.holdings]
            name = SCREENSHOT_NAME
        else:
            portfolio = state.get("portfolio")
            if portfolio is None or not portfolio.holdings:
                return Prepared(context=NO_PORTFOLIO_CONTEXT)
            holdings, name = portfolio.holdings, portfolio.name
        run.inputs.update(holdings=holdings, risk_profile=risk_profile)
        analysis = await self._portfolios.analyze(holdings, risk_profile=risk_profile)
        facts: dict[str, Any] = {"portfolio_name": name, **analysis_facts(analysis)}
        if shot is not None and shot.holdings:
            self._record_screenshot(run, shot, analysis)
            facts["source"] = "holdings read from the user's screenshot; values use live prices"
        self._record(run, analysis, name)
        return Prepared(
            context=as_data("portfolio_analysis", to_json(facts)),
            data={"analysis": analysis, "name": name},
        )

    def _record_screenshot(
        self, run: AgentRun, shot: ScreenshotRead, analysis: PortfolioAnalysis
    ) -> None:
        live = {h.symbol: h for h in analysis.holdings}
        rows = []
        for h in shot.holdings:
            metrics = live.get(h.symbol)
            rows.append(
                {
                    "symbol": h.symbol,
                    "name": (metrics.name if metrics and metrics.name else h.name) or "",
                    "quantity": h.quantity,
                    "screenshot_price": h.price,
                    "live_price": metrics.price if metrics else None,
                    "market_value": metrics.market_value if metrics else None,
                }
            )
        run.artifacts.append(
            Artifact(
                kind="screenshot_holdings",
                title="Holdings read from your screenshot",
                data={
                    "rows": rows,
                    "unpriced": analysis.unpriced,
                    "freshness": [f.model_dump(mode="json") for f in analysis.freshness],
                },
            )
        )

    def _record(self, run: AgentRun, analysis: PortfolioAnalysis, name: str) -> None:
        for stamp in analysis.freshness:
            run.stamp(stamp)
        freshness = [f.model_dump(mode="json") for f in analysis.freshness]
        run.artifacts.append(
            Artifact(
                kind="portfolio_metrics",
                title=f"{name}: key metrics",
                data={
                    "total_value": analysis.total_value,
                    "total_gain": analysis.total_gain,
                    "total_gain_percent": analysis.total_gain_percent,
                    "diversification_score": analysis.diversification.score,
                    "weighted_beta": analysis.risk.weighted_beta,
                    "volatility_percent": analysis.risk.annualized_volatility_percent,
                    "max_drawdown_percent": analysis.risk.max_drawdown_percent,
                    "weighted_expense_ratio": analysis.weighted_expense_ratio,
                    "benchmark": (
                        analysis.benchmark.model_dump(mode="json") if analysis.benchmark else None
                    ),
                    "freshness": freshness,
                },
            )
        )
        run.artifacts.append(
            Artifact(
                kind="allocation",
                title=f"{name}: allocation",
                data={
                    "by_asset_class": [
                        s.model_dump(mode="json") for s in analysis.allocation_by_asset_class
                    ],
                    "by_sector": [s.model_dump(mode="json") for s in analysis.allocation_by_sector],
                    "freshness": freshness,
                },
            )
        )

    # --- Tools ---------------------------------------------------------------

    async def _analyze_tool(self, run: AgentRun, args: AnalyzeHoldingsArgs) -> str:
        holdings = [HoldingInput(symbol=h.symbol, quantity=h.quantity) for h in args.holdings]
        analysis = await self._portfolios.analyze(holdings)
        if not analysis.holdings:
            return to_json(
                {"error": "none of these symbols could be priced", **analysis_facts(analysis)}
            )
        self._record(run, analysis, "Holdings you listed")
        return to_json(analysis_facts(analysis))

    async def _benchmark_tool(self, run: AgentRun, args: BenchmarkArgs) -> str:
        holdings: Sequence[HoldingInput] = run.inputs.get("holdings", ())
        if not holdings:
            return "Error: there is no portfolio to compare."
        analysis = await self._portfolios.analyze(
            holdings, risk_profile=run.inputs.get("risk_profile"), benchmark_range=args.range
        )
        for stamp in analysis.freshness:
            run.stamp(stamp)
        if analysis.benchmark is None:
            return f"Not enough shared price history to compare over {args.range.value}."
        return to_json(analysis.benchmark.model_dump(mode="json"))

    async def _details_tool(self, run: AgentRun, args: SymbolArgs) -> str:
        sourced = await self._market.get_reference_data(args.symbol)
        run.stamp(sourced.freshness)
        ref = sourced.value
        return to_json(
            {
                "symbol": ref.symbol,
                "name": ref.name,
                "asset_class": ref.asset_class.value,
                "sector": ref.sector,
                "beta": ref.beta,
                "expense_ratio_percent": _pct(ref.expense_ratio, 2),
                "status": sourced.freshness.status.value,
            }
        )

    # --- Without an LLM ------------------------------------------------------

    def offline_answer(self, state: FinanceState, run: AgentRun, prepared: Prepared) -> str:
        analysis: PortfolioAnalysis | None = prepared.data.get("analysis")
        if analysis is None:
            return NO_PORTFOLIO_ANSWER
        if not analysis.holdings:
            return (
                "I couldn't price any of the holdings in your portfolio right now, so I can't "
                "analyze it. Please try again later."
            )
        lines = [f"**{prepared.data['name']}** is worth {format_usd(analysis.total_value)}."]
        if analysis.total_gain is not None and analysis.total_gain_percent is not None:
            lines[0] += (
                f" Against what you paid, that's {format_usd(analysis.total_gain)} "
                f"({format_percent(analysis.total_gain_percent, signed=True)})."
            )
        mix = ", ".join(
            f"{s.label} {format_percent(s.weight * 100, decimals=0)}"
            for s in analysis.allocation_by_asset_class
        )
        lines.append(f"By asset class: {mix}.")
        lines.append(
            f"The diversification score is **{analysis.diversification.score}/100**. "
            + " ".join(analysis.diversification.drivers)
        )
        risk = analysis.risk
        if risk.annualized_volatility_percent is not None:
            swing = format_percent(risk.annualized_volatility_percent, decimals=1)
            text = (
                "Replaying today's holdings over the past year, the portfolio swung about "
                f"{swing} a year (annualized volatility)"
            )
            if risk.max_drawdown_percent is not None:
                drop = format_percent(abs(risk.max_drawdown_percent), decimals=1)
                text += f", and its worst fall from a peak was {drop}"
            lines.append(f"{text}.")
        if analysis.benchmark is not None:
            b = analysis.benchmark
            mine = format_percent(b.portfolio_return_percent, signed=True)
            theirs = format_percent(b.benchmark_return_percent, signed=True)
            lines.append(
                f"Over {b.range}, it returned {mine} versus {theirs} for {b.benchmark_symbol}."
            )
        if analysis.observations:
            lines.append("Things worth understanding:")
            lines.extend(f"- {o.message}" for o in analysis.observations)
        return "\n\n".join(lines)

    def confidence(self, run: AgentRun, prepared: Prepared) -> float:
        return 0.85 if run.artifacts else 0.4

    def follow_ups(self, state: FinanceState, run: AgentRun, prepared: Prepared) -> list[str]:
        if not run.artifacts:
            return [
                "What makes a portfolio diversified?",
                "What is an expense ratio?",
                "How is portfolio risk measured?",
            ]
        return [
            "What does the diversification score measure?",
            "How do fund fees add up over time?",
            "What is beta, and why does it matter?",
        ]
