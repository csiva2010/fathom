"""Load and validate data/kb/glossary.yaml (KB-02)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from src.rag.models import GlossaryTerm


@dataclass
class GlossaryResult:
    terms: list[GlossaryTerm] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def load_glossary(path: Path) -> GlossaryResult:
    result = GlossaryResult()
    if not path.exists():
        result.errors.append(f"{path.name}: file not found")
        return result

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("terms", []) if isinstance(raw, dict) else []
    seen: set[str] = set()
    for position, entry in enumerate(entries, start=1):
        try:
            term = GlossaryTerm.model_validate(entry)
        except ValidationError as error:
            result.errors.append(f"glossary entry {position}: {error.errors()[0]['msg']}")
            continue
        key = term.term.lower()
        if key in seen:
            result.errors.append(f"glossary entry {position}: duplicate term '{term.term}'")
            continue
        seen.add(key)
        result.terms.append(term)
    return result
