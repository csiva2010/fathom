"""Turn one graph run into chat events for the SSE stream (CH-01, CH-03 to CH-06, OR-06).

Event order for an answered turn:

    route -> agent_start x N -> token ... -> artifact ... -> citation ... -> freshness ...
          -> (replace) -> done

`trace` events (one per finished node, OR-08) interleave with the others as nodes finish;
`done` repeats the whole trace on the message, so the client can rely on that alone.

Which LLM tokens stream live:
- one agent planned: that agent's tokens (its answer passes through the synthesizer);
- several agents: only the synthesizer's merge call, never interleaved agent drafts.
The router's and compliance's LLM calls never stream.

The client's text must equal the final answer before `done`. When the draft and then the
compliance-checked final answer arrive, they are reconciled with what was streamed: an
extension (notes, disclaimer, an offline answer that streamed nothing) goes out as a
`token`; anything else (a compliance rewrite, a retried agent) as a `replace`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from pydantic import BaseModel, Field

from src.core.domain.market import Freshness
from src.core.errors import AppError
from src.core.logging import get_logger
from src.rag.models import Citation
from src.workflow.compliance import FINAL_ANSWER_KEY
from src.workflow.screenshot import SCREENSHOT_KEY, ScreenshotInput
from src.workflow.state import (
    AgentName,
    Artifact,
    FinalAnswer,
    RoutePlan,
    TraceEvent,
    UserContext,
)

log = get_logger(__name__)

AGENT_NODES = frozenset(a.value for a in AgentName)
DRAFT_NODES = frozenset({"synthesizer", "clarify", "advice_redirect"})

AnswerKind = Literal["answer", "clarification", "redirect"]
ATTACHMENT_KEY = "attachment"  # marks a user message that came with a screenshot


class ChatMessage(BaseModel):
    """One message in a conversation, as the chat UI renders it."""

    id: str
    role: Literal["user", "assistant"]
    content: str
    kind: AnswerKind = "answer"
    agents: list[AgentName] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    freshness: list[Freshness] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    has_image: bool = False  # a user message sent with a screenshot (the image isn't kept)
    trace: list[TraceEvent] = Field(default_factory=list)  # "How I answered" (INN-01)


# --- Events ------------------------------------------------------------------


class RouteEvent(BaseModel):
    """The router's plan: which agents will answer (CH-03 badges show from here)."""

    type: Literal["route"] = "route"
    kind: AnswerKind
    agents: list[AgentName]
    confidence: float


class AgentStartEvent(BaseModel):
    type: Literal["agent_start"] = "agent_start"
    agent: AgentName


class TokenEvent(BaseModel):
    """Text to append to the answer."""

    type: Literal["token"] = "token"
    text: str


class ReplaceEvent(BaseModel):
    """Supersedes everything streamed so far (a compliance rewrite, a retried agent)."""

    type: Literal["replace"] = "replace"
    text: str


class TraceStepEvent(BaseModel):
    """A workflow node finished: its timing, LLM usage and tool calls (OR-08)."""

    type: Literal["trace"] = "trace"
    step: TraceEvent


class ArtifactEvent(BaseModel):
    type: Literal["artifact"] = "artifact"
    artifact: Artifact


class CitationEvent(BaseModel):
    """A source card; `number` matches the answer's [n] marker."""

    type: Literal["citation"] = "citation"
    number: int
    citation: Citation


class FreshnessEvent(BaseModel):
    type: Literal["freshness"] = "freshness"
    freshness: Freshness


class DoneEvent(BaseModel):
    """The finished, compliance-checked message. The client should render this one."""

    type: Literal["done"] = "done"
    message: ChatMessage


class ErrorEvent(BaseModel):
    """The turn failed; uses the same fields as the REST error envelope."""

    type: Literal["error"] = "error"
    code: str
    message: str
    retryable: bool = False


ChatEvent = Annotated[
    RouteEvent
    | AgentStartEvent
    | TraceStepEvent
    | TokenEvent
    | ReplaceEvent
    | ArtifactEvent
    | CitationEvent
    | FreshnessEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]


# --- Messages ----------------------------------------------------------------


def to_chat_message(final: FinalAnswer, message_id: str) -> ChatMessage:
    return ChatMessage(
        id=message_id,
        role="assistant",
        content=final.answer_md,
        kind=final.kind,
        agents=final.agents,
        citations=final.citations,
        artifacts=final.artifacts,
        freshness=final.freshness,
        follow_ups=final.follow_ups,
        trace=final.trace,
    )


def history(messages: list[AnyMessage]) -> list[ChatMessage]:
    """A checkpointed thread's messages as the UI shows them (user questions, answers)."""
    out: list[ChatMessage] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            out.append(
                ChatMessage(
                    id=message.id or "",
                    role="user",
                    content=message.text,
                    has_image=message.additional_kwargs.get(ATTACHMENT_KEY) == "image",
                )
            )
        elif isinstance(message, AIMessage) and message.text.strip():
            saved = message.additional_kwargs.get(FINAL_ANSWER_KEY)
            if saved:
                out.append(to_chat_message(FinalAnswer.model_validate(saved), message.id or ""))
            else:
                out.append(ChatMessage(id=message.id or "", role="assistant", content=message.text))
    return out


# --- Stream ------------------------------------------------------------------


def _kind(plan: RoutePlan) -> AnswerKind:
    if plan.needs_clarification:
        return "clarification"
    return "redirect" if plan.is_advice_request else "answer"


class _Reconciler:
    """Tracks the text the client has and emits what brings it to a target text."""

    def __init__(self) -> None:
        self.text = ""

    def append(self, text: str) -> TokenEvent:
        self.text += text
        return TokenEvent(text=text)

    def settle(self, target: str) -> TokenEvent | ReplaceEvent | None:
        if target == self.text:
            return None
        if target.startswith(self.text):
            return self.append(target[len(self.text) :])
        self.text = target
        return ReplaceEvent(text=target)


async def stream_turn(
    graph: Any,
    *,
    thread_id: str,
    user: UserContext,
    text: str,
    turn_id: str,
    image: ScreenshotInput | None = None,
) -> AsyncIterator[ChatEvent]:
    """Run one turn on a conversation thread and yield chat events. Never raises."""
    question = HumanMessage(text, id=f"{turn_id}-q")
    configurable: dict[str, Any] = {"thread_id": thread_id}
    if image is not None:
        question.additional_kwargs[ATTACHMENT_KEY] = "image"
        configurable[SCREENSHOT_KEY] = image  # config, not state: never checkpointed
    inputs = {"messages": [question], "user": user, "turn_id": turn_id}
    config = {"configurable": configurable}
    client = _Reconciler()
    live_node: str | None = None  # an agent name, "synthesizer", or None (nothing streams)

    try:
        async for mode, chunk in graph.astream(inputs, config, stream_mode=["messages", "updates"]):
            if mode == "messages":
                message, meta = chunk
                node = meta.get("langgraph_node")
                live = node == live_node or (live_node == "agent" and node in AGENT_NODES)
                # Streaming providers send chunks; others one whole message per call.
                if live and isinstance(message, AIMessage) and message.text:
                    yield client.append(message.text)
                continue

            for node, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                for step in update.get("trace") or []:
                    yield TraceStepEvent(step=step)
                if node == "router" and update.get("plan") is not None:
                    plan: RoutePlan = update["plan"]
                    kind = _kind(plan)
                    yield RouteEvent(kind=kind, agents=plan.agents, confidence=plan.confidence)
                    if kind == "answer":
                        live_node = "agent" if len(plan.agents) == 1 else "synthesizer"
                        for agent in plan.agents:
                            yield AgentStartEvent(agent=agent)
                elif node in AGENT_NODES:
                    for output in update.get("agent_outputs") or []:
                        for artifact in output.artifacts:
                            yield ArtifactEvent(artifact=artifact)
                elif node in DRAFT_NODES and update.get("draft") is not None:
                    live_node = None  # anything after the draft is compliance's business
                    event = client.settle(update["draft"].answer_md)
                    if event is not None:
                        yield event
                elif node == "compliance" and update.get("final") is not None:
                    final: FinalAnswer = update["final"]
                    for number, citation in enumerate(final.citations, start=1):
                        yield CitationEvent(number=number, citation=citation)
                    for stamp in final.freshness:
                        yield FreshnessEvent(freshness=stamp)
                    event = client.settle(final.answer_md)
                    if event is not None:
                        yield event
                    yield DoneEvent(message=to_chat_message(final, turn_id))
    except AppError as error:
        log.warning("chat turn failed", extra={"code": error.code, "thread_id": thread_id})
        yield ErrorEvent(code=error.code, message=error.message, retryable=error.retryable)
    except Exception:
        log.exception("chat turn crashed", extra={"thread_id": thread_id})
        yield ErrorEvent(
            code="internal_error",
            message="Something went wrong while answering. Please try again.",
            retryable=True,
        )
