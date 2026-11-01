"""Reproducible KB ingestion (KB-07): validate -> chunk -> keyword index -> report.

Day 1 builds the keyword (BM25) index. The embedding step (Gemini primary + OpenAI
fallback collections in ChromaDB) plugs in here on day 2 behind the same pipeline.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.core.config.settings import KnowledgeBaseConfig
from src.rag.ingestion.article_loader import load_articles
from src.rag.ingestion.chunker import chunk_article
from src.rag.ingestion.glossary_loader import load_glossary
from src.rag.keyword.bm25_index import BM25Index
from src.rag.models import Chunk

GLOSSARY_FILENAME = "glossary.yaml"
REPORT_FILENAME = "ingestion_report.json"


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

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


def run_ingestion(
    config: KnowledgeBaseConfig,
    source_dir: Path,
    index_dir: Path,
    *,
    strict: bool = True,
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
    )
    (index_dir / REPORT_FILENAME).write_text(report.to_json(), encoding="utf-8")
    return report
