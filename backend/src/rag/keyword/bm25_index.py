"""BM25 keyword index over KB chunks, persisted as JSON next to the vector store (KB-05).

Stored as JSON (chunks + tokens) rather than a pickle so it is safe to load and easy to
inspect; the BM25 statistics are rebuilt in memory on load, which takes milliseconds.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from src.rag.keyword.tokenizer import tokenize
from src.rag.models import Chunk

INDEX_FILENAME = "bm25_index.json"


@dataclass(frozen=True)
class KeywordHit:
    chunk: Chunk
    score: float


class BM25Index:
    def __init__(self, chunks: list[Chunk], tokens: list[list[str]] | None = None):
        if not chunks:
            raise ValueError("cannot build a BM25 index with no chunks")
        self.chunks = chunks
        self.tokens = tokens or [self._document_tokens(c) for c in chunks]
        self._vocab = [set(t) for t in self.tokens]
        self._bm25 = BM25Okapi(self.tokens)

    @staticmethod
    def _document_tokens(chunk: Chunk) -> list[str]:
        # Title and section heading are indexed too, so "Roth IRA" finds the right article.
        return tokenize(f"{chunk.title} {chunk.section} {chunk.text}")

    def search(self, query: str, k: int = 20, category: str | None = None) -> list[KeywordHit]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        # A chunk is a hit if it shares any query term. We don't filter on score > 0:
        # BM25 IDF is zero for a term in exactly half the chunks, common in small categories.
        wanted = set(query_tokens)
        candidates = [
            i
            for i, vocab in enumerate(self._vocab)
            if vocab & wanted and (not category or self.chunks[i].category == category)
        ]
        scores = self._bm25.get_scores(query_tokens)
        candidates.sort(key=lambda i: scores[i], reverse=True)
        return [KeywordHit(self.chunks[i], float(scores[i])) for i in candidates[:k]]

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / INDEX_FILENAME
        payload = {
            "chunks": [c.model_dump() for c in self.chunks],
            "tokens": self.tokens,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    @classmethod
    def load(cls, directory: Path) -> BM25Index:
        payload = json.loads((directory / INDEX_FILENAME).read_text(encoding="utf-8"))
        chunks = [Chunk.model_validate(c) for c in payload["chunks"]]
        return cls(chunks, payload["tokens"])
