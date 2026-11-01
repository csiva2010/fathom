"""Split a Markdown file into YAML front matter and body."""

from __future__ import annotations

from typing import Any

import yaml

DELIMITER = "---"


class FrontMatterError(ValueError):
    pass


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != DELIMITER:
        raise FrontMatterError("file must start with '---' front matter")
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == DELIMITER)
    except StopIteration as error:
        raise FrontMatterError("front matter is not closed with '---'") from error

    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as error:
        raise FrontMatterError(f"invalid YAML front matter: {error}") from error
    if not isinstance(meta, dict):
        raise FrontMatterError("front matter must be a YAML mapping")

    body = "\n".join(lines[end + 1 :]).strip()
    return meta, body
