"""Load and validate KB articles from data/kb/<category>/<article>.md (KB-03)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from src.rag.ingestion.front_matter import FrontMatterError, split_front_matter
from src.rag.models import Article, ArticleMeta


@dataclass
class LoadResult:
    articles: list[Article] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def load_articles(source_dir: Path, categories: list[str], levels: list[str]) -> LoadResult:
    result = LoadResult()
    seen_ids: dict[str, str] = {}

    for path in sorted(source_dir.glob("*/*.md")):
        relative = str(path.relative_to(source_dir))
        try:
            raw_meta, body = split_front_matter(path.read_text(encoding="utf-8"))
            meta = ArticleMeta.model_validate(raw_meta)
        except (FrontMatterError, ValidationError) as error:
            result.errors.append(f"{relative}: {_short(error)}")
            continue

        problems = _check_consistency(meta, path, categories, levels, seen_ids, body)
        if problems:
            result.errors.extend(f"{relative}: {p}" for p in problems)
            continue

        seen_ids[meta.id] = relative
        result.articles.append(Article(meta=meta, body=body, path=relative))
    return result


def _check_consistency(
    meta: ArticleMeta,
    path: Path,
    categories: list[str],
    levels: list[str],
    seen_ids: dict[str, str],
    body: str,
) -> list[str]:
    problems: list[str] = []
    if categories and meta.category not in categories:
        problems.append(f"unknown category '{meta.category}'")
    if path.parent.name != meta.category:
        problems.append(f"category '{meta.category}' does not match folder '{path.parent.name}'")
    if levels and meta.level not in levels:
        problems.append(f"unknown level '{meta.level}'")
    if meta.id in seen_ids:
        problems.append(f"duplicate id '{meta.id}' (also in {seen_ids[meta.id]})")
    if len(body.split()) < 50:
        problems.append("body is shorter than 50 words")
    return problems


def _short(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()
        )
    return str(error)
