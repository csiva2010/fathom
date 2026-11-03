"""Agent execution with timeout and retry, plus the fallback handler (OR-07).

Each agent node runs with a timeout and retries once. A failure never crashes the graph:
it writes a `NodeError`, and the fallback handler turns errors into short notes that the
synthesizer shows with whatever the other agents produced.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from src.core.errors import AppError
from src.core.logging import get_logger
from src.workflow.state import AgentName, AgentOutput, FinanceState, NodeError, TraceEvent
from src.workflow.tracing import TraceStep, trace_step

log = get_logger(__name__)


class Agent(Protocol):
    @property
    def name(self) -> AgentName: ...

    async def run(self, state: FinanceState) -> AgentOutput: ...


class AgentNode:
    def __init__(self, agent: Agent, *, timeout_seconds: float, retries: int):
        self._agent = agent
        self._timeout = timeout_seconds
        self._retries = retries

    async def __call__(self, state: FinanceState) -> dict[str, Any]:
        with trace_step(self._agent.name.value) as step:
            return await self._run(state, step)

    async def _run(self, state: FinanceState, step: TraceStep) -> dict[str, Any]:
        name = self._agent.name.value
        error: NodeError | None = None
        for attempt in range(self._retries + 1):
            try:
                output = await asyncio.wait_for(self._agent.run(state), self._timeout)
            except AppError as failure:
                error = NodeError(
                    node=name,
                    code=failure.code,
                    message=failure.message,
                    retryable=failure.retryable,
                )
                if not failure.retryable:
                    break
            except TimeoutError:
                error = NodeError(
                    node=name,
                    code="timeout",
                    message=f"took longer than {self._timeout:g} seconds",
                    retryable=True,
                )
            except Exception as failure:
                log.exception("agent failed", extra={"agent": name})
                error = NodeError(node=name, code="agent_error", message=type(failure).__name__)
            else:
                return {
                    "agent_outputs": [output],
                    "trace": [self._trace(step, attempt, output=output)],
                }
            log.warning(
                "agent attempt failed",
                extra={"agent": name, "attempt": attempt + 1, "code": error.code},
            )
        assert error is not None
        return {"errors": [error], "trace": [self._trace(step, self._retries, error=error)]}

    def _trace(
        self,
        step: TraceStep,
        attempt: int,
        *,
        output: AgentOutput | None = None,
        error: NodeError | None = None,
    ) -> TraceEvent:
        detail: dict[str, Any] = {"attempts": attempt + 1}
        if output is not None:
            detail.update(
                citations=len(output.citations),
                sources=[c.title for c in output.citations],
                artifacts=[a.kind for a in output.artifacts],
                confidence=output.confidence,
                grounded=output.grounded,
            )
        if error is not None:
            detail["error"] = error.code
        return step.event(**detail)


async def agent_unavailable_node(state: dict[str, Any]) -> dict[str, Any]:
    """Target for planned agents that are not wired into the graph yet."""
    agent = AgentName(state["agent"])
    return {
        "errors": [
            NodeError(
                node=agent.value,
                code="agent_unavailable",
                message=f"{agent.label} isn't available yet",
            )
        ],
        "trace": [
            TraceEvent(node=agent.value, latency_ms=0, detail={"error": "agent_unavailable"})
        ],
    }


def describe_error(error: NodeError) -> str:
    try:
        label = AgentName(error.node).label
    except ValueError:
        label = error.node
    if error.code == "agent_unavailable":
        return f"{label} isn't available yet, so this answer doesn't cover that part."
    if error.code == "timeout":
        return f"{label} took too long to respond, so this answer may be incomplete."
    if error.code == "unknown_symbol":
        return error.message
    return f"{label} ran into a problem ({error.code}), so this answer may be incomplete."


def fallback_node(state: FinanceState) -> dict[str, Any]:
    """Turn agent errors into user-facing notes; the turn still completes."""
    errors = state.get("errors") or []
    return {"notes": [describe_error(e) for e in errors]} if errors else {}
