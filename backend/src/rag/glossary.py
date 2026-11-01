"""Glossary lookups for the define_term tool and hover definitions (KB-02)."""

from __future__ import annotations

import difflib
import re

from src.rag.models import GlossaryTerm

_QUESTION_PREFIX = re.compile(
    r"^(please\s+)?(define|explain|what\s+(is|are|does)|what's|meaning\s+of|"
    r"tell\s+me\s+about)\s+(an?\s+|the\s+)?",
    re.IGNORECASE,
)
_TRAILING = re.compile(r"(\s+mean)?[\s?.!]*$", re.IGNORECASE)


def normalise_term(text: str) -> str:
    text = " ".join(text.strip().split())
    text = _QUESTION_PREFIX.sub("", text)
    text = _TRAILING.sub("", text)
    return text.lower().strip("\"'")


class Glossary:
    def __init__(self, terms: list[GlossaryTerm]):
        self.terms = sorted(terms, key=lambda t: t.term.lower())
        self._by_key: dict[str, GlossaryTerm] = {}
        for term in self.terms:
            for key in (term.term, *term.aliases):
                self._by_key.setdefault(key.lower(), term)

    def __len__(self) -> int:
        return len(self.terms)

    def lookup(self, text: str) -> GlossaryTerm | None:
        """Exact match on the term or an alias, tolerating "what is a ...?" and plurals."""
        key = normalise_term(text)
        if not key:
            return None
        for candidate in (key, key.removesuffix("s"), key.removesuffix("es")):
            if candidate in self._by_key:
                return self._by_key[candidate]
        return None

    def suggest(self, text: str, limit: int = 3) -> list[str]:
        key = normalise_term(text)
        matches = difflib.get_close_matches(key, list(self._by_key), n=limit * 2, cutoff=0.6)
        names: list[str] = []
        for match in matches:
            name = self._by_key[match].term
            if name not in names:
                names.append(name)
        return names[:limit]

    def search(self, query: str, limit: int = 20) -> list[GlossaryTerm]:
        """Terms whose name or alias contains the query (Learn tab, hover lookups)."""
        needle = query.strip().lower()
        if not needle:
            return self.terms[:limit]
        return [
            t
            for t in self.terms
            if needle in t.term.lower() or any(needle in a.lower() for a in t.aliases)
        ][:limit]
