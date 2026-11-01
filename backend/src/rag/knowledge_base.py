"""The knowledge base as the agents and API see it: hybrid retriever plus glossary.

Loaded once at startup. If the BM25 index is missing it is rebuilt from the source files
(keyword only, no API calls); run `scripts.ingest_kb` to add the vector collections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.core.config import Settings, resolve_path
from src.core.logging import get_logger
from src.rag.catalog import ArticleCatalog
from src.rag.embeddings import Embedder, build_embedders
from src.rag.glossary import Glossary
from src.rag.ingestion.article_loader import load_articles
from src.rag.ingestion.glossary_loader import load_glossary
from src.rag.ingestion.pipeline import GLOSSARY_FILENAME, IngestionFailed, run_ingestion
from src.rag.keyword.bm25_index import INDEX_FILENAME, BM25Index
from src.rag.reranker import Reranker, build_reranker
from src.rag.retriever import HybridRetriever
from src.rag.vector_store import ChromaVectorStore

log = get_logger(__name__)


@dataclass
class KnowledgeBase:
    retriever: HybridRetriever
    glossary: Glossary
    catalog: ArticleCatalog = field(default_factory=lambda: ArticleCatalog([]))


def load_knowledge_base(
    settings: Settings,
    *,
    embedders: list[Embedder] | None = None,
    reranker: Reranker | None = None,
) -> KnowledgeBase | None:
    """Build the KB from the saved index; None if there is no usable KB at all."""
    kb = settings.kb
    source_dir = resolve_path(kb.source_dir)
    index_dir = resolve_path(kb.index_dir)

    if not (index_dir / INDEX_FILENAME).exists():
        try:
            run_ingestion(kb, source_dir, index_dir, strict=False)
            log.info("keyword index built at startup", extra={"index_dir": str(index_dir)})
        except IngestionFailed as failure:
            log.error("knowledge base unavailable", extra={"errors": failure.errors[:5]})
            return None

    index = BM25Index.load(index_dir)
    embedders = build_embedders(settings) if embedders is None else embedders
    vector_dir = resolve_path(kb.vector_dir)
    vector_store = ChromaVectorStore(vector_dir) if embedders and _has_store(vector_dir) else None
    retriever = HybridRetriever(
        index,
        reranker or build_reranker(kb.reranker),
        kb.retrieval,
        vector_store=vector_store,
        embedders=embedders,
    )
    glossary = Glossary(load_glossary(source_dir / GLOSSARY_FILENAME).terms)
    # Ingestion already validated the files; invalid ones are skipped here, not fatal.
    catalog = ArticleCatalog(load_articles(source_dir, kb.categories, kb.levels).articles)
    log.info(
        "knowledge base loaded",
        extra={
            "chunks": retriever.chunk_count,
            "glossary_terms": len(glossary),
            "articles": len(catalog),
            "vector_search": vector_store is not None,
        },
    )
    return KnowledgeBase(retriever=retriever, glossary=glossary, catalog=catalog)


def _has_store(directory: Path) -> bool:
    return directory.is_dir() and any(directory.iterdir())
