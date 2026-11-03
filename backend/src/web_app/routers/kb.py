"""Learn tab API (KB-08): browse and search articles, look up glossary terms.

`/kb/search` returns ranked passages from the same hybrid retriever the chat agents use;
the MCP server's search_knowledge_base tool calls it (MCP-01, MCP-02).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from src.core.errors import ConfigurationError, NotFound
from src.rag.catalog import category_label, reading_minutes, summarize
from src.rag.knowledge_base import KnowledgeBase
from src.rag.models import Article, GlossaryTerm
from src.rag.retriever import citation_for
from src.web_app.auth.current_user import CurrentUserDep
from src.web_app.dependencies import ContainerDep
from src.web_app.schemas.kb import (
    ArticleList,
    ArticleOut,
    ArticleSummary,
    CategoryOut,
    GlossaryList,
    KbSearchHit,
    KbSearchOut,
)

router = APIRouter(prefix="/kb", tags=["learn"])


def _kb(container: ContainerDep) -> KnowledgeBase:
    if container.knowledge_base is None:
        raise ConfigurationError("The knowledge base isn't available right now.")
    return container.knowledge_base


def _summary(article: Article) -> ArticleSummary:
    meta = article.meta
    return ArticleSummary(
        id=meta.id,
        title=meta.title,
        category=meta.category,
        category_label=category_label(meta.category),
        level=meta.level,
        summary=summarize(article.body),
        tags=meta.tags,
        source_name=meta.source_name,
        source_url=str(meta.source_url),
        last_reviewed=meta.last_reviewed,
        reading_minutes=reading_minutes(article.body),
    )


@router.get("/articles", response_model=ArticleList, summary="Browse and search articles")
def list_articles(
    _user: CurrentUserDep,
    container: ContainerDep,
    category: str | None = None,
    level: str | None = None,
    q: Annotated[str, Query(max_length=200)] = "",
) -> ArticleList:
    kb = _kb(container)
    counts = kb.catalog.category_counts()
    order = container.settings.kb.categories or sorted(counts)
    return ArticleList(
        articles=[_summary(a) for a in kb.catalog.search(q, category=category, level=level)],
        categories=[
            CategoryOut(id=c, label=category_label(c), count=counts.get(c, 0))
            for c in order
            if counts.get(c)
        ],
        levels=container.settings.kb.levels,
    )


@router.get("/articles/{article_id}", response_model=ArticleOut, summary="One article")
def get_article(article_id: str, _user: CurrentUserDep, container: ContainerDep) -> ArticleOut:
    catalog = _kb(container).catalog
    article = catalog.get(article_id)
    if article is None:
        raise NotFound("That article doesn't exist.")
    return ArticleOut(
        **_summary(article).model_dump(),
        body_md=article.body,
        related=[_summary(a) for a in catalog.related(article_id)],
    )


@router.get("/search", response_model=KbSearchOut, summary="Ranked passages for a question")
async def search_passages(
    _user: CurrentUserDep,
    container: ContainerDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    category: str | None = None,
    level: str | None = None,
) -> KbSearchOut:
    result = await _kb(container).retriever.search(q, category=category, level=level)
    return KbSearchOut(
        query=result.query,
        mode=result.mode,
        results=[
            KbSearchHit(citation=citation_for(hit.chunk), text=hit.chunk.text, score=hit.score)
            for hit in result.chunks
        ],
    )


@router.get("/glossary", response_model=GlossaryList, summary="Search the glossary")
def search_glossary(
    _user: CurrentUserDep,
    container: ContainerDep,
    q: Annotated[str, Query(max_length=80)] = "",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> GlossaryList:
    glossary = _kb(container).glossary
    return GlossaryList(terms=glossary.search(q, limit), total=len(glossary))


@router.get("/glossary/{term}", response_model=GlossaryTerm, summary="Define one term")
def define_term(term: str, _user: CurrentUserDep, container: ContainerDep) -> GlossaryTerm:
    found = _kb(container).glossary.lookup(term)
    if found is None:
        raise NotFound(f"'{term}' isn't in the glossary.")
    return found
