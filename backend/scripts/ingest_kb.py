"""Rebuild the knowledge-base index from data/kb (KB-07).

Usage (from backend/):  python -m scripts.ingest_kb [--lenient]
"""

from __future__ import annotations

import argparse
import sys

from src.core.config import get_settings, resolve_path
from src.rag.ingestion.pipeline import IngestionFailed, run_ingestion


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lenient", action="store_true", help="skip invalid files instead of failing the build"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        report = run_ingestion(
            settings.kb,
            resolve_path(settings.kb.source_dir),
            resolve_path(settings.kb.index_dir),
            strict=not args.lenient,
        )
    except IngestionFailed as failure:
        print(f"Ingestion failed: {failure}", file=sys.stderr)
        for error in failure.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(report.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
