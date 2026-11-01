"""Hybrid retrieval: vectors + BM25, reciprocal rank fusion, rerank, threshold (KB-05, KB-06).

1. Top `vector_k` from the primary embedding collection. If embedding or search fails, the
   next configured embedder and its own collection are tried; if all fail, BM25 alone.
2. Top `keyword_k` from BM25. Both lists are merged with reciprocal rank fusion.
3. The fused candidates are reranked (0..1) and anything below the reranker's threshold is
   dropped. Chunks at the user's level get a small boost for ordering only.
4. Nothing left means NO_CONTEXT: the agent says it doesn't know instead of guessing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from src.core.config.settings import RetrievalConfig
from src.core.logging import get_logger
from src.rag.embeddings import Embedder
from src.rag.keyword.bm25_index import BM25Index
from src.rag.models import Chunk, Citation
from src.rag.reranker import Reranker
from src.rag.vector_store import VectorSearch

log = get_logger(__name__)

MAX_QUERY_CHARS = 1000


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float  # reranker relevance, 0..1


@dataclass
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    mode: str = "keyword"  # "hybrid:<collection>" or "keyword"

    @property
    def found(self) -> bool:
        return bool(self.chunks)

    def citations_per_chunk(self) -> list[Citation]:
        """The citation for each retrieved chunk, in rank order (may repeat a section)."""
        return [citation_for(hit.chunk) for hit in self.chunks]

    @property
    def citations(self) -> list[Citation]:
        """One citation per article section, in rank order (CH-04)."""
        citations: list[Citation] = []
        for citation in self.citations_per_chunk():
            if citation not in citations:
                citations.append(citation)
        return citations


def citation_for(chunk: Chunk) -> Citation:
    return Citation(
        article_id=chunk.article_id,
        title=chunk.title,
        section=chunk.section,
        source_name=chunk.source_name,
        source_url=chunk.source_url,
    )


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], k: int) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


class HybridRetriever:
    def __init__(
        self,
        index: BM25Index,
        reranker: Reranker,
        config: RetrievalConfig,
        *,
        vector_store: VectorSearch | None = None,
        embedders: Sequence[Embedder] = (),
    ):
        self._index = index
        self._chunks = {c.id: c for c in index.chunks}
        self._reranker = reranker
        self._config = config
        self._vectors = vector_store
        self._embedders = list(embedders)

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    async def search(
        self, query: str, *, category: str | None = None, level: str | None = None
    ) -> RetrievalResult:
        query = " ".join(query.split())[:MAX_QUERY_CHARS]
        if not query:
            return RetrievalResult(query=query)

        keyword_ids = [
            hit.chunk.id for hit in self._index.search(query, self._config.keyword_k, category)
        ]
        vector_ids, mode = await self._vector_search(query, category)
        fused = reciprocal_rank_fusion([vector_ids, keyword_ids], self._config.rrf_k)
        ranked = sorted(fused, key=lambda cid: fused[cid], reverse=True)
        candidates = [self._chunks[cid] for cid in ranked[: self._config.rerank_candidates]]
        if not candidates:
            return RetrievalResult(query=query, mode=mode)

        scores = await asyncio.to_thread(self._reranker.score, query, candidates)
        kept = [
            RetrievedChunk(chunk, score)
            for chunk, score in zip(candidates, scores, strict=True)
            if score >= self._reranker.min_score
        ]

        def ordering(hit: RetrievedChunk) -> float:
            boost = self._config.level_boost if level and hit.chunk.level == level else 0.0
            return hit.score + boost

        kept.sort(key=ordering, reverse=True)
        return RetrievalResult(query=query, chunks=kept[: self._config.top_n], mode=mode)

    async def _vector_search(self, query: str, category: str | None) -> tuple[list[str], str]:
        if self._vectors is None:
            return [], "keyword"
        for embedder in self._embedders:
            try:
                embedding = await embedder.embed_query(query)
                hits = await asyncio.to_thread(
                    self._vectors.query,
                    embedder.collection,
                    embedding,
                    self._config.vector_k,
                    category,
                )
            except Exception as error:  # provider outage, missing collection, bad key
                log.warning(
                    "vector search failed, trying next embedder",
                    extra={"collection": embedder.collection, "error": str(error)},
                )
                continue
            # A stale collection may hold ids the current index no longer has.
            return [h.chunk_id for h in hits if h.chunk_id in self._chunks], (
                f"hybrid:{embedder.collection}"
            )
        return [], "keyword"
