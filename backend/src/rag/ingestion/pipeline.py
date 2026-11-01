"""Reproducible KB ingestion (KB-07): validate -> chunk -> BM25 -> embed -> report.

Each configured embedder (Gemini primary, OpenAI fallback) gets its own ChromaDB collection,
rebuilt from scratch so reruns are idempotent. An embedder that fails is reported and
skipped: retrieval then falls back to the other collection or to BM25 alone.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.core.config.settings import KnowledgeBaseConfig
from src.core.logging import get_logger
from src.data.resilience import clock as default_clock
from src.data.resilience.sliding_window import SlidingWindowLimiter
from src.rag.embeddings import Embedder
from src.rag.ingestion.article_loader import load_articles
from src.rag.ingestion.chunker import chunk_article
from src.rag.ingestion.glossary_loader import load_glossary
from src.rag.keyword.bm25_index import BM25Index
from src.rag.models import Chunk
from src.rag.vector_store import ChromaVectorStore

log = get_logger(__name__)

GLOSSARY_FILENAME = "glossary.yaml"
REPORT_FILENAME = "ingestion_report.json"
RATE_LIMIT_RETRIES = 3
DEFAULT_RETRY_SECONDS = 30.0
_RATE_LIMITED = re.compile(r"\b429\b|RESOURCE_EXHAUSTED|rate.?limit", re.IGNORECASE)
_RETRY_AFTER = re.compile(r"retry in ([0-9.]+)\s*s", re.IGNORECASE)


class IngestionFailed(RuntimeError):
    def __init__(self, errors: list[str]):
        super().__init__(f"{len(errors)} knowledge-base problem(s) found")
        self.errors = errors


@dataclass
class IngestionReport:
    articles: int
    chunks: int
    glossary_terms: int
    by_category: dict[str, int]
    by_level: dict[str, int]
    empty_categories: list[str]
    built_at: str
    errors: list[str] = field(default_factory=list)
    vector_collections: dict[str, int] = field(default_factory=dict)
    vector_skipped: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


def run_ingestion(
    config: KnowledgeBaseConfig,
    source_dir: Path,
    index_dir: Path,
    *,
    strict: bool = True,
    embedders: Sequence[Embedder] = (),
    vector_dir: Path | None = None,
    embed_batch_size: int = 64,
) -> IngestionReport:
    loaded = load_articles(source_dir, config.categories, config.levels)
    glossary = load_glossary(source_dir / GLOSSARY_FILENAME)
    errors = loaded.errors + glossary.errors
    if errors and strict:
        raise IngestionFailed(errors)
    if not loaded.articles:
        raise IngestionFailed(errors or ["no articles found"])

    chunks: list[Chunk] = []
    for article in loaded.articles:
        chunks.extend(chunk_article(article, config.chunk_tokens, config.chunk_overlap))

    BM25Index(chunks).save(index_dir)

    collections: dict[str, int] = {}
    skipped: list[str] = []
    if embedders and vector_dir is not None:
        store = ChromaVectorStore(vector_dir)
        for embedder in embedders:
            try:
                vectors = asyncio.run(embed_chunks(embedder, chunks, embed_batch_size))
                collections[embedder.collection] = store.rebuild(
                    embedder.collection, chunks, vectors
                )
            except Exception as error:  # provider outage or bad key: keep BM25 working
                log.warning(
                    "embedding failed",
                    extra={"collection": embedder.collection, "error": str(error)},
                )
                skipped.append(f"{embedder.collection}: {error}")

    by_category = Counter(a.meta.category for a in loaded.articles)
    report = IngestionReport(
        articles=len(loaded.articles),
        chunks=len(chunks),
        glossary_terms=len(glossary.terms),
        by_category=dict(sorted(by_category.items())),
        by_level=dict(sorted(Counter(a.meta.level for a in loaded.articles).items())),
        empty_categories=[c for c in config.categories if c not in by_category],
        built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        errors=errors,
        vector_collections=collections,
        vector_skipped=skipped,
    )
    (index_dir / REPORT_FILENAME).write_text(report.to_json(), encoding="utf-8")
    return report


def retry_delay(error: Exception) -> float | None:
    """Seconds to wait if `error` is a rate-limit (429) response, else None."""
    message = str(error)
    if not _RATE_LIMITED.search(message):
        return None
    hint = _RETRY_AFTER.search(message)
    return float(hint.group(1)) + 1.0 if hint else DEFAULT_RETRY_SECONDS


async def embed_chunks(
    embedder: Embedder,
    chunks: Sequence[Chunk],
    batch_size: int,
    *,
    clock: default_clock.Clock = default_clock.monotonic,
    sleep: default_clock.Sleeper = default_clock.sleep,
) -> list[list[float]]:
    """Embed chunk text (with title and section for context) in batches.

    Batches are paced to the model's per-minute quota, and a 429 is retried after the
    delay the provider asks for, so free-tier keys can ingest the whole KB.
    """
    texts = [f"{c.title}\n{c.section}\n{c.text}" for c in chunks]
    limit = embedder.requests_per_minute
    if limit:
        batch_size = min(batch_size, limit)
    limiter = SlidingWindowLimiter(limit, clock=clock, sleep=sleep) if limit else None

    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        if limiter is not None:
            await limiter.acquire(len(batch))
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                vectors.extend(await embedder.embed_documents(batch))
                break
            except Exception as error:
                delay = retry_delay(error)
                if delay is None or attempt == RATE_LIMIT_RETRIES:
                    raise
                log.info(
                    "embedding rate limited, waiting",
                    extra={"collection": embedder.collection, "seconds": delay},
                )
                await sleep(delay)
        log.info(
            "embedded batch",
            extra={"collection": embedder.collection, "done": len(vectors), "total": len(texts)},
        )
    if len(vectors) != len(chunks):
        raise ValueError(f"expected {len(chunks)} vectors, got {len(vectors)}")
    return vectors
