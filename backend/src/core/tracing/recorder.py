"""Per-step usage recorder for traces (OR-08, INN-01).

A workflow node opens `recording()`; while it is open, the LLM gateway records each model
call (model, tokens, fallbacks) and agents record each tool they call. The node then puts
the totals on its trace event. Nothing is recorded when no step is open, so the gateway and
agents work the same outside the graph (scripts, MCP-backed routes, tests).

The current recorder lives in a context variable. LangGraph runs each node in its own task
with a copy of the context, so parallel agents never write into each other's recorder,
while tasks a node starts itself (an agent under `asyncio.wait_for`) share the node's.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepRecorder:
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    fallbacks: int = 0  # calls answered by a model other than the first choice
    models: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    def add_llm_call(
        self, model: str, usage: Mapping[str, Any] | None, *, fallback: bool = False
    ) -> None:
        self.llm_calls += 1
        self.fallbacks += int(fallback)
        if model not in self.models:
            self.models.append(model)
        if usage:
            self.input_tokens += int(usage.get("input_tokens") or 0)
            self.output_tokens += int(usage.get("output_tokens") or 0)


_current: ContextVar[StepRecorder | None] = ContextVar("trace_step", default=None)


def current_step() -> StepRecorder | None:
    return _current.get()


@contextmanager
def recording() -> Iterator[StepRecorder]:
    """Collect LLM and tool usage for the code inside the block."""
    recorder = StepRecorder()
    token = _current.set(recorder)
    try:
        yield recorder
    finally:
        _current.reset(token)


def record_llm_call(model: str, usage: Mapping[str, Any] | None, *, fallback: bool = False) -> None:
    recorder = _current.get()
    if recorder is not None:
        recorder.add_llm_call(model, usage, fallback=fallback)


def record_tool(name: str) -> None:
    recorder = _current.get()
    if recorder is not None:
        recorder.tools.append(name)
