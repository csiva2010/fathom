"""Trace steps for workflow nodes (OR-08, INN-01).

    with trace_step("router") as step:
        ...  # LLM calls and tool calls in here are recorded
        return {"plan": plan, "trace": [step.event(method="llm")]}

`event()` stamps the time since the step opened and the LLM and tool usage recorded so
far, so call it last. The events feed the structured logs, the SSE `trace` events and the
"How I answered" panel under each answer.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from src.core.tracing import StepRecorder, recording
from src.workflow.state import TraceEvent


class TraceStep:
    def __init__(self, node: str, recorder: StepRecorder):
        self.node = node
        self.recorder = recorder
        self._started = time.perf_counter()

    def event(self, **detail: Any) -> TraceEvent:
        usage = self.recorder
        return TraceEvent(
            node=self.node,
            latency_ms=round((time.perf_counter() - self._started) * 1000),
            llm_calls=usage.llm_calls,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            models=list(usage.models),
            fallbacks=usage.fallbacks,
            tools=list(usage.tools),
            detail=detail,
        )


@contextmanager
def trace_step(node: str) -> Iterator[TraceStep]:
    with recording() as recorder:
        yield TraceStep(node, recorder)
