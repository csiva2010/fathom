"""Rerankers score (query, chunk) pairs from 0 to 1 for the relevance threshold (KB-05).

The cross-encoder (ms-marco-MiniLM-L-6-v2, self-hosted) is the confirmed choice. It loads
once, lazily, and falls back to the lexical reranker if sentence-transformers or the
weights are unavailable, so retrieval never breaks because of the reranker.
"""

from __future__ import annotations

import threading
from typing import Any, Protocol

from src.core.config.settings import RerankerConfig
from src.core.logging import get_logger
from src.rag.keyword.tokenizer import tokenize
from src.rag.models import Chunk

log = get_logger(__name__)


def chunk_text(chunk: Chunk) -> str:
    return f"{chunk.title}. {chunk.section}. {chunk.text}"


class Reranker(Protocol):
    @property
    def min_score(self) -> float: ...

    def score(self, query: str, chunks: list[Chunk]) -> list[float]: ...


class LexicalReranker:
    """Share of the query's terms found in the chunk. No model, deterministic."""

    def __init__(self, min_score: float):
        self._min_score = min_score

    @property
    def min_score(self) -> float:
        return self._min_score

    def score(self, query: str, chunks: list[Chunk]) -> list[float]:
        wanted = set(tokenize(query))
        if not wanted:
            return [0.0 for _ in chunks]
        return [len(wanted & set(tokenize(chunk_text(c)))) / len(wanted) for c in chunks]


class CrossEncoderReranker:
    def __init__(self, model_name: str, min_score: float, fallback: LexicalReranker):
        self._model_name = model_name
        self._min_score = min_score
        self._fallback = fallback
        self._model: Any = None
        self._failed = False
        self._lock = threading.Lock()

    @property
    def min_score(self) -> float:
        return self._fallback.min_score if self._failed else self._min_score

    def _load(self) -> Any:
        with self._lock:
            if self._model is None and not self._failed:
                try:
                    from sentence_transformers import CrossEncoder

                    self._model = CrossEncoder(self._model_name)
                except Exception as error:  # missing package, weights or network
                    log.warning(
                        "cross-encoder unavailable, using lexical reranker",
                        extra={"model": self._model_name, "error": str(error)},
                    )
                    self._failed = True
            return self._model

    def warm_up(self) -> bool:
        return self._load() is not None

    def score(self, query: str, chunks: list[Chunk]) -> list[float]:
        if not chunks:
            return []
        model = self._load()
        if model is None:
            return self._fallback.score(query, chunks)
        import torch

        scores = model.predict(
            [(query, chunk_text(c)) for c in chunks], activation_fn=torch.nn.Sigmoid()
        )
        return [float(s) for s in scores]


def build_reranker(config: RerankerConfig) -> Reranker:
    lexical = LexicalReranker(config.lexical_min_score)
    if config.kind == "lexical":
        return lexical
    return CrossEncoderReranker(config.model, config.cross_encoder_min_score, lexical)
