"""Answers that skip the agents: clarifying questions (OR-02) and advice redirects (OR-03).

The redirect is a fixed template on purpose: it can never drift into a recommendation, and
it still offers the educational path (concepts, data for the ticker) instead.
"""

from __future__ import annotations

from typing import Any

from src.workflow.state import FinalAnswer, FinanceState, TraceEvent

REDIRECT_TEMPLATE = """I can't tell you whether to buy, sell or hold{subject}. I'm an educational \
tool, not a financial adviser, and I don't know your full situation.

What I can do is help you think it through the way investors do:

- **Look at the data**: recent price moves, the 50- and 200-day moving averages, the \
52-week range and volatility{data_subject}.
- **Understand the concepts**: valuation, diversification, and how a single holding \
affects a portfolio's risk.
- **Check the fit**: how an investment lines up with your goals, time horizon and risk \
tolerance.

For a personal decision, a fee-only fiduciary adviser can look at your whole picture."""


def advice_redirect_node(state: FinanceState) -> dict[str, Any]:
    plan = state.get("plan")
    tickers = plan.tickers if plan else []
    joined = " or ".join(tickers)
    answer = REDIRECT_TEMPLATE.format(
        subject=f" {joined}" if joined else " a specific investment",
        data_subject=f" for {joined}" if joined else "",
    )
    follow_ups = [f"Show me {tickers[0]}'s price trend and volatility"] if tickers else []
    follow_ups += [
        "How do investors evaluate a stock?",
        "What does diversification protect against?",
    ]
    return {
        "draft": FinalAnswer(kind="redirect", answer_md=answer, follow_ups=follow_ups[:3]),
        "trace": [TraceEvent(node="advice_redirect", latency_ms=0, detail={"tickers": tickers})],
    }


def clarify_node(state: FinanceState) -> dict[str, Any]:
    plan = state.get("plan")
    question = (plan.clarifying_question if plan else None) or (
        "Could you tell me a bit more about what you'd like to know?"
    )
    return {
        "draft": FinalAnswer(
            kind="clarification",
            answer_md=question,
            follow_ups=[
                "Explain what an index fund is",
                "How is the market doing today?",
                "How much should I save for an emergency fund?",
            ],
        ),
        "trace": [TraceEvent(node="clarify", latency_ms=0)],
    }
