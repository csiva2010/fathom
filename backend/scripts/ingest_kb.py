"""Rebuild the knowledge-base index from data/kb (KB-07).

Builds the BM25 index and, for each configured embedding model with an API key, a fresh
ChromaDB collection. Safe to rerun: every output is rebuilt from the source files.

Usage (from backend/):  python -m scripts.ingest_kb [--lenient] [--keyword-only]
"""

from __future__ import annotations

import argparse
import sys

from src.core.config import get_settings, resolve_path
from src.rag.embeddings import build_embedders
from src.rag.ingestion.pipeline import IngestionFailed, run_ingestion


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lenient", action="store_true", help="skip invalid files instead of failing the build"
    )
    parser.add_argument(
        "--keyword-only", action="store_true", help="build only the BM25 index (no API calls)"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    embedders = [] if args.keyword_only else build_embedders(settings)
    try:
        report = run_ingestion(
            settings.kb,
            resolve_path(settings.kb.source_dir),
            resolve_path(settings.kb.index_dir),
            strict=not args.lenient,
            embedders=embedders,
            vector_dir=resolve_path(settings.kb.vector_dir),
            embed_batch_size=settings.kb.embed_batch_size,
        )
    except IngestionFailed as failure:
        print(f"Ingestion failed: {failure}", file=sys.stderr)
        for error in failure.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(report.to_json())
    if not embedders and not args.keyword_only:
        print("No embedding API keys set: built the keyword index only.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
