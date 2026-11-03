"""Provider-agnostic LLM gateway with ordered fallback (D1, NF-R02).

Agents and workflow nodes call the gateway, never a vendor SDK. Each call tries the
configured models in order (Gemini Flash first, then Claude); a failure is logged and the
next model answers. If every model fails the caller gets `LLMUnavailable` and degrades.
Each answered call is recorded (model, tokens, fallback) on the open trace step, if any.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel

from src.core.config import Settings
from src.core.config.settings import LlmModelConfig
from src.core.errors import LLMUnavailable
from src.core.logging import get_logger
from src.core.tracing import record_llm_call

log = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class NamedModel:
    name: str  # "<provider>:<model>", used in logs and traces
    model: BaseChatModel


class LLMGateway:
    def __init__(self, models: Sequence[NamedModel]):
        self._models = list(models)

    @property
    def available(self) -> bool:
        return bool(self._models)

    @property
    def model_names(self) -> list[str]:
        return [m.name for m in self._models]

    async def ainvoke(
        self, messages: Sequence[BaseMessage], *, tools: Sequence[dict[str, Any]] = ()
    ) -> AIMessage:
        """One chat turn; with `tools`, the reply may contain tool calls."""

        async def call(named: NamedModel) -> tuple[AIMessage, AIMessage]:
            runnable: Any = named.model.bind_tools(list(tools)) if tools else named.model
            reply = await runnable.ainvoke(list(messages))
            if not isinstance(reply, AIMessage):
                raise TypeError(f"expected AIMessage, got {type(reply).__name__}")
            return reply, reply

        return cast(AIMessage, await self._with_fallback("chat", call))

    async def astructured(self, schema: type[T], messages: Sequence[BaseMessage]) -> T:
        """Structured output parsed into `schema` (router, compliance rewrite)."""

        async def call(named: NamedModel) -> tuple[T, Any]:
            # include_raw keeps the provider message, so the call's token usage is traced.
            runnable = named.model.with_structured_output(schema, include_raw=True)
            result: dict[str, Any] = cast(dict[str, Any], await runnable.ainvoke(list(messages)))
            if result.get("parsing_error") is not None:
                raise result["parsing_error"]
            parsed = result.get("parsed")
            if parsed is None:
                raise ValueError(f"no {schema.__name__} in the model's reply")
            value = parsed if isinstance(parsed, schema) else schema.model_validate(parsed)
            return value, result.get("raw")

        return cast(T, await self._with_fallback("structured", call))

    async def _with_fallback(self, kind: str, call: Any) -> Any:
        if not self._models:
            raise LLMUnavailable("No language model is configured.")
        last_error: Exception | None = None
        for position, named in enumerate(self._models):
            started = time.perf_counter()
            try:
                result, raw = await call(named)
            except Exception as error:
                last_error = error
                log.warning(
                    "llm call failed",
                    extra={
                        "model": named.name,
                        "kind": kind,
                        "error": f"{type(error).__name__}: {error}"[:300],
                        "fallback_available": position + 1 < len(self._models),
                    },
                )
                continue
            if position > 0:
                log.info("llm fallback used", extra={"model": named.name, "kind": kind})
            record_llm_call(named.name, getattr(raw, "usage_metadata", None), fallback=position > 0)
            log.debug(
                "llm call",
                extra={
                    "model": named.name,
                    "kind": kind,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                },
            )
            return result
        raise LLMUnavailable("The language models are unavailable right now.") from last_error


def _build_chat_model(config: LlmModelConfig, api_key: str) -> BaseChatModel:
    if config.provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=config.model,
            google_api_key=api_key,
            temperature=config.temperature,
            max_output_tokens=config.max_output_tokens,
            timeout=config.timeout_seconds,
            max_retries=1,
        )
    if config.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return cast(
            BaseChatModel,
            ChatAnthropic(
                model=config.model,
                api_key=api_key,
                temperature=config.temperature,
                max_tokens=config.max_output_tokens,
                timeout=config.timeout_seconds,
                max_retries=1,
            ),
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=config.model,
        api_key=api_key,
        temperature=config.temperature,
        max_completion_tokens=config.max_output_tokens,
        timeout=config.timeout_seconds,
        max_retries=1,
    )


def build_llm_gateway(settings: Settings) -> LLMGateway:
    models: list[NamedModel] = []
    for config in settings.llm.models:
        api_key = settings.provider_api_key(config.provider)
        if not api_key:
            log.info(
                "chat model skipped: no API key",
                extra={"provider": config.provider, "model": config.model},
            )
            continue
        models.append(
            NamedModel(f"{config.provider}:{config.model}", _build_chat_model(config, api_key))
        )
    return LLMGateway(models)
