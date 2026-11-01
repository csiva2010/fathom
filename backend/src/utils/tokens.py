"""Cheap token estimates (about 0.75 English words per token) without a tokenizer dependency."""

from __future__ import annotations

WORDS_PER_TOKEN = 0.75


def estimate_tokens(text: str) -> int:
    return round(len(text.split()) / WORDS_PER_TOKEN)


def tokens_to_words(tokens: int) -> int:
    return max(1, int(tokens * WORDS_PER_TOKEN))
