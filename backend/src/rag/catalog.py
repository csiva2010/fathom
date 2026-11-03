"""The article catalog behind the Learn tab (KB-08): browse by category and level, search.

Search is a simple field-weighted keyword match over titles, tags and bodies. Browsing
should be predictable and free, so it does not use the hybrid retriever (which calls an
embedding API and drops weak matches below its relevance threshold).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from src.rag.keyword.tokenizer import tokenize
from src.rag.models import Article

SUMMARY_WORDS = 40
WORDS_PER_MINUTE = 200
LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}

CATEGORY_LABELS = {
    "basics": "Basics",
    "stocks": "Stocks",
    "bonds": "Bonds",
    "funds_etfs": "Funds & ETFs",
    "retirement": "Retirement",
    "tax": "Tax",
    "risk_diversification": "Risk & diversification",
    "budgeting_saving": "Budgeting & saving",
    "market_mechanics": "How markets work",
    "behavioral_finance": "Investor behavior",
}

_HEADING = re.compile(r"^#{1,6}\s")


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").capitalize())


def summarize(body: str, words: int = SUMMARY_WORDS) -> str:
    """The first paragraph that isn't a heading, cut to about `words` words."""
    for paragraph in body.split("\n\n"):
        text = " ".join(paragraph.split())
        if text and not _HEADING.match(paragraph.strip()):
            parts = text.split()
            return " ".join(parts[:words]) + ("…" if len(parts) > words else "")
    return ""


def reading_minutes(body: str) -> int:
    """Whole minutes to read the article at an average pace (at least one)."""
    return max(1, round(len(body.split()) / WORDS_PER_MINUTE))


@dataclass(frozen=True)
class _Entry:
    article: Article
    title: frozenset[str]
    tags: frozenset[str]
    body: Counter[str]


class ArticleCatalog:
    def __init__(self, articles: list[Article]):
        self._entries = [
            _Entry(
                article=a,
                title=frozenset(tokenize(a.meta.title)),
                tags=frozenset(tokenize(" ".join(a.meta.tags))),
                body=Counter(tokenize(a.body)),
            )
            for a in sorted(articles, key=lambda a: a.meta.title.lower())
        ]
        self._by_id = {e.article.meta.id: e.article for e in self._entries}

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, article_id: str) -> Article | None:
        return self._by_id.get(article_id)

    def category_counts(self) -> dict[str, int]:
        return dict(Counter(e.article.meta.category for e in self._entries))

    def search(
        self, query: str = "", *, category: str | None = None, level: str | None = None
    ) -> list[Article]:
        """Filtered articles; with a query, best matches first and non-matches dropped."""
        entries = [
            e
            for e in self._entries
            if (category is None or e.article.meta.category == category)
            and (level is None or e.article.meta.level == level)
        ]
        terms = tokenize(query)
        if not terms:
            return [e.article for e in entries]
        scored = []
        for entry in entries:
            score = sum(
                3 * (t in entry.title) + 2 * (t in entry.tags) + min(entry.body[t], 5) * 0.2
                for t in terms
            )
            # Every term must appear somewhere, so multi-word queries narrow the list.
            if all(t in entry.title or t in entry.tags or entry.body[t] for t in terms):
                scored.append((score, entry.article))
        scored.sort(key=lambda pair: -pair[0])
        return [article for _, article in scored]

    def related(self, article_id: str, limit: int = 3) -> list[Article]:
        """Articles to read next: shared tags and title words first, then the same
        category; at equal relevance, the same or next level up before others."""
        source = next((e for e in self._entries if e.article.meta.id == article_id), None)
        if source is None:
            return []
        meta = source.article.meta
        level = LEVEL_ORDER.get(meta.level, 0)
        scored = []
        for entry in self._entries:
            other = entry.article.meta
            if other.id == article_id:
                continue
            score: float = 2 * len(source.tags & entry.tags) + len(source.title & entry.title)
            score += 1.5 * (other.category == meta.category)
            if score <= 0:
                continue
            step = LEVEL_ORDER.get(other.level, 0) - level
            scored.append((-score, 0 if step in (0, 1) else 1, entry.article.meta.title, entry))
        scored.sort(key=lambda item: item[:3])
        return [item[3].article for item in scored[:limit]]
