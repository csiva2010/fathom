from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from src.rag.models import Citation, GlossaryTerm


class CategoryOut(BaseModel):
    id: str
    label: str
    count: int


class ArticleSummary(BaseModel):
    id: str
    title: str
    category: str
    category_label: str
    level: str
    summary: str
    tags: list[str]
    source_name: str
    source_url: str
    last_reviewed: date


class ArticleList(BaseModel):
    articles: list[ArticleSummary]
    categories: list[CategoryOut]  # every category, with counts over the whole KB
    levels: list[str]


class ArticleOut(ArticleSummary):
    body_md: str


class GlossaryList(BaseModel):
    terms: list[GlossaryTerm]
    total: int


class KbSearchHit(BaseModel):
    citation: Citation
    text: str
    score: float  # reranker relevance, 0..1


class KbSearchOut(BaseModel):
    """Retrieved passages for a question (KB-05). Empty `results` means nothing relevant."""

    query: str
    mode: str  # "hybrid:<collection>" or "keyword"
    results: list[KbSearchHit]
