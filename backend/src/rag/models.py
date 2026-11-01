"""Knowledge-base models shared by ingestion, retrieval and agents."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, HttpUrl


class ArticleMeta(BaseModel):
    """YAML front matter required on every KB article (KB-03). Missing fields fail ingestion."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=3)
    category: str
    level: str
    source_url: HttpUrl
    source_name: str = Field(min_length=2)
    last_reviewed: date
    tags: list[str] = Field(default_factory=list)


class Article(BaseModel):
    meta: ArticleMeta
    body: str
    path: str


class Chunk(BaseModel):
    id: str  # "<article_id>#<n>"
    article_id: str
    title: str
    section: str
    category: str
    level: str
    source_url: str
    source_name: str
    text: str
    token_estimate: int


class GlossaryTerm(BaseModel):
    term: str = Field(min_length=1)
    definition: str = Field(min_length=10)
    level: str = "beginner"
    related: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)  # e.g. "exchange-traded fund" for ETF


class Citation(BaseModel):
    """What the UI shows on a source card (CH-04)."""

    article_id: str
    title: str
    section: str
    source_name: str
    source_url: str
