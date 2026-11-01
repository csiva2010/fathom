"""Embedding models behind one small interface (KB-04).

Gemini `gemini-embedding-2` is primary and OpenAI `text-embedding-3-small` the fallback
(confirmed decision). Each embedder names the Chroma collection that holds its vectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from langchain_core.embeddings import Embeddings

from src.core.config import Settings
from src.core.config.settings import EmbeddingModelConfig
from src.core.logging import get_logger

log = get_logger(__name__)


class Embedder(Protocol):
    @property
    def collection(self) -> str: ...

    @property
    def requests_per_minute(self) -> int | None:
        """Ingestion pacing for this model's quota; None means no limit."""
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


@dataclass
class LangChainEmbedder:
    """Adapts a LangChain `Embeddings` model to the `Embedder` protocol."""

    collection: str
    model: Embeddings
    requests_per_minute: int | None = None

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self.model.aembed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        return await self.model.aembed_query(text)


def _build_model(config: EmbeddingModelConfig, api_key: str) -> Embeddings:
    if config.provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(model=config.model, google_api_key=api_key)
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=config.model, api_key=api_key)  # type: ignore[call-arg]


def build_embedders(settings: Settings) -> list[Embedder]:
    """Embedders in configured order, skipping any whose API key is missing."""
    embedders: list[Embedder] = []
    for config in settings.kb.embeddings:
        api_key = settings.provider_api_key(config.provider)
        if not api_key:
            log.info(
                "embedding model skipped: no API key",
                extra={"provider": config.provider, "model": config.model},
            )
            continue
        embedders.append(
            LangChainEmbedder(
                config.collection, _build_model(config, api_key), config.requests_per_minute
            )
        )
    return embedders
