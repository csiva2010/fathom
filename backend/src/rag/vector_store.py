"""Persistent ChromaDB vector store for KB chunks (KB-04).

Chunks are keyed by `article_id#n` and carry category and level metadata so retrieval can
filter by category. Each ingestion rebuilds a collection from scratch, which keeps the
store identical to the source files (KB-07).
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError

from src.rag.models import Chunk


@dataclass(frozen=True)
class VectorHit:
    chunk_id: str
    distance: float


class VectorSearch(Protocol):
    def query(
        self, collection: str, embedding: list[float], k: int, category: str | None = None
    ) -> list[VectorHit]: ...


class ChromaVectorStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(directory), settings=ChromaSettings(anonymized_telemetry=False)
        )

    def rebuild(
        self,
        collection: str,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
        batch_size: int = 500,
    ) -> int:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        with contextlib.suppress(NotFoundError):
            self._client.delete_collection(collection)
        target = self._client.create_collection(
            collection, configuration={"hnsw": {"space": "cosine"}}, embedding_function=None
        )
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            metadatas: list[Any] = [
                {"article_id": c.article_id, "category": c.category, "level": c.level}
                for c in batch
            ]
            target.add(
                ids=[c.id for c in batch],
                embeddings=cast(Any, [list(e) for e in embeddings[start : start + batch_size]]),
                metadatas=metadatas,
            )
        return target.count()

    def count(self, collection: str) -> int:
        try:
            return self._client.get_collection(collection).count()
        except NotFoundError:
            return 0

    def query(
        self, collection: str, embedding: list[float], k: int, category: str | None = None
    ) -> list[VectorHit]:
        """Nearest chunks by cosine distance. Raises NotFoundError if never ingested."""
        target = self._client.get_collection(collection)
        result = target.query(
            query_embeddings=cast(Any, [embedding]),
            n_results=k,
            where={"category": category} if category else None,
            include=["distances"],
        )
        ids = result["ids"][0] if result["ids"] else []
        distances = (result.get("distances") or [[]])[0]
        return [VectorHit(chunk_id, float(d)) for chunk_id, d in zip(ids, distances, strict=True)]
