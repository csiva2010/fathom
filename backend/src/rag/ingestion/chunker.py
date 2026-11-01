"""Heading-aware chunking: split by Markdown headings, then into ~N-token windows with overlap.

Each chunk keeps its article's metadata plus the section heading it came from (KB-04).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.rag.models import Article, Chunk
from src.utils.tokens import estimate_tokens, tokens_to_words

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
MIN_SECTION_WORDS = 25


@dataclass
class Section:
    heading: str
    text: str


def split_sections(body: str, default_heading: str) -> list[Section]:
    sections: list[Section] = []
    heading = default_heading
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections.append(Section(heading, text))

    for line in body.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            buffer = []
            heading = match.group(2)
        else:
            buffer.append(line)
    flush()
    return _merge_tiny(sections)


def _merge_tiny(sections: list[Section]) -> list[Section]:
    """Fold very short sections into the next one so chunks carry enough context."""
    merged: list[Section] = []
    carry: Section | None = None
    for section in sections:
        if carry is not None:
            section = Section(carry.heading, f"{carry.text}\n\n{section.text}")
            carry = None
        if len(section.text.split()) < MIN_SECTION_WORDS:
            carry = section
        else:
            merged.append(section)
    if carry is not None:
        if merged:
            last = merged[-1]
            merged[-1] = Section(last.heading, f"{last.text}\n\n{carry.text}")
        else:
            merged.append(carry)
    return merged


def window_words(text: str, max_words: int, overlap_words: int) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    step = max(1, max_words - overlap_words)
    windows: list[str] = []
    for start in range(0, len(words), step):
        windows.append(" ".join(words[start : start + max_words]))
        if start + max_words >= len(words):
            break
    return windows


def chunk_article(article: Article, chunk_tokens: int, overlap: float) -> list[Chunk]:
    meta = article.meta
    max_words = tokens_to_words(chunk_tokens)
    overlap_words = int(max_words * overlap)

    chunks: list[Chunk] = []
    for section in split_sections(article.body, default_heading=meta.title):
        for text in window_words(section.text, max_words, overlap_words):
            chunks.append(
                Chunk(
                    id=f"{meta.id}#{len(chunks)}",
                    article_id=meta.id,
                    title=meta.title,
                    section=section.heading,
                    category=meta.category,
                    level=meta.level,
                    source_url=str(meta.source_url),
                    source_name=meta.source_name,
                    text=text,
                    token_estimate=estimate_tokens(text),
                )
            )
    return chunks
