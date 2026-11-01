"""Test doubles for LLMs, embeddings and rerankers. No test touches the network."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from src.core.llm.gateway import LLMGateway, NamedModel
from src.rag.keyword.tokenizer import tokenize
from src.rag.models import Chunk


class ScriptedChatModel(BaseChatModel):
    """Replies with queued AIMessages (or raises queued exceptions), recording every call.

    `bind_tools` returns the model itself, so tool calls and LangChain's default
    structured output (a forced tool call named after the schema) both work.
    """

    replies: list[Any] = []
    calls: list[list[BaseMessage]] = []
    bound_tools: list[Any] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Any:  # type: ignore[override]
        self.bound_tools.append(list(tools))
        return self

    def _next(self, messages: list[BaseMessage]) -> ChatResult:
        self.calls.append(list(messages))
        if not self.replies:
            raise AssertionError("ScriptedChatModel ran out of replies")
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, str):
            reply = AIMessage(reply)
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._next(messages)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._next(messages)


def scripted(*replies: Any) -> ScriptedChatModel:
    return ScriptedChatModel(replies=list(replies), calls=[], bound_tools=[])


def gateway(*replies: Any) -> tuple[LLMGateway, ScriptedChatModel]:
    model = scripted(*replies)
    return LLMGateway([NamedModel("fake:primary", model)]), model


def tool_call(name: str, args: dict[str, Any], call_id: str = "call-1") -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": call_id}])


def structured(schema_name: str, **args: Any) -> AIMessage:
    """The reply LangChain's default with_structured_output expects."""
    return tool_call(schema_name, args)


class HashEmbedder:
    """Bag-of-words hashing embedder: texts sharing words get similar vectors."""

    def __init__(self, collection: str = "kb_test", *, fail: bool = False, dims: int = 64):
        self.collection = collection
        self.requests_per_minute: int | None = None
        self.fail = fail
        self.dims = dims
        self.calls = 0

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dims
        for token in tokenize(text):
            index = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dims
            vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("embedding provider down")
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("embedding provider down")
        return self._vector(text)


class FixedReranker:
    """Scores chunks from a lookup by article id (default 0.9)."""

    def __init__(self, scores: dict[str, float] | None = None, min_score: float = 0.5):
        self.scores = scores or {}
        self._min_score = min_score

    @property
    def min_score(self) -> float:
        return self._min_score

    def score(self, query: str, chunks: list[Chunk]) -> list[float]:
        return [self.scores.get(c.article_id, 0.9) for c in chunks]
