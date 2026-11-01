"""Quality gate for the real knowledge base in data/kb (KB-01 to KB-03)."""

from __future__ import annotations

from collections import Counter

from src.core.config import Settings, resolve_path
from src.rag.ingestion.article_loader import load_articles
from src.rag.ingestion.glossary_loader import load_glossary

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]
SOURCE = resolve_path(SETTINGS.kb.source_dir)


def test_articles_meet_kb_targets() -> None:
    loaded = load_articles(SOURCE, SETTINGS.kb.categories, SETTINGS.kb.levels)
    assert loaded.errors == []
    assert len(loaded.articles) >= 100  # KB-01
    per_category = Counter(a.meta.category for a in loaded.articles)
    assert set(per_category) == set(SETTINGS.kb.categories)
    assert min(per_category.values()) >= 10
    assert {a.meta.level for a in loaded.articles} == set(SETTINGS.kb.levels)


def test_every_article_has_sections_and_attribution() -> None:
    for article in load_articles(SOURCE, SETTINGS.kb.categories, SETTINGS.kb.levels).articles:
        assert article.body.count("\n## ") >= 2, article.path
        assert len(article.body.split()) >= 150, article.path
        assert article.meta.source_url.scheme == "https", article.path


def test_glossary_meets_target_and_links_resolve() -> None:
    glossary = load_glossary(SOURCE / "glossary.yaml")
    assert glossary.errors == []
    assert len(glossary.terms) >= 200  # KB-02
    names = {t.term.lower() for t in glossary.terms} | {
        a.lower() for t in glossary.terms for a in t.aliases
    }
    unresolved = {r for t in glossary.terms for r in t.related if r.lower() not in names}
    assert unresolved == set()
    assert {t.level for t in glossary.terms} <= set(SETTINGS.kb.levels)
