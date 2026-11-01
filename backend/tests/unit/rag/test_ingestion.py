from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.core.config.settings import KnowledgeBaseConfig
from src.rag.ingestion.article_loader import load_articles
from src.rag.ingestion.chunker import chunk_article, split_sections, window_words
from src.rag.ingestion.front_matter import FrontMatterError, split_front_matter
from src.rag.ingestion.glossary_loader import load_glossary
from src.rag.ingestion.pipeline import IngestionFailed, run_ingestion
from src.rag.keyword.bm25_index import BM25Index
from src.rag.keyword.tokenizer import tokenize
from src.rag.models import Article, ArticleMeta, Chunk

FIXTURE_KB = Path(__file__).parents[2] / "fixtures" / "kb"
KB_CONFIG = KnowledgeBaseConfig(categories=["basics", "tax"], chunk_tokens=120)

FRONT = """---
id: {id}
title: Sample Title
category: {category}
level: beginner
source_url: https://example.org/a
source_name: Example
last_reviewed: 2026-10-29
---
"""


def write_article(root: Path, category: str, article_id: str, body: str) -> None:
    folder = root / category
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{article_id}.md").write_text(
        FRONT.format(id=article_id, category=category) + body, encoding="utf-8"
    )


LONG_BODY = "# Heading\n\n" + " ".join(["word"] * 80)


# --- Front matter ------------------------------------------------------------


def test_split_front_matter() -> None:
    meta, body = split_front_matter("---\nid: a\n---\n\nHello")
    assert meta == {"id": "a"}
    assert body == "Hello"


@pytest.mark.parametrize(
    "text",
    ["no front matter", "---\nid: a\nnever closed", "---\n[1, 2\n---\nbody", "---\n- a\n---\nb"],
)
def test_front_matter_errors(text: str) -> None:
    with pytest.raises(FrontMatterError):
        split_front_matter(text)


# --- Article loading ---------------------------------------------------------


def test_load_fixture_articles() -> None:
    result = load_articles(FIXTURE_KB, ["basics", "tax"], ["beginner", "intermediate"])
    assert result.errors == []
    assert {a.meta.id for a in result.articles} == {"compound-growth", "hsa-basics"}


def test_loader_reports_every_problem(tmp_path: Path) -> None:
    write_article(tmp_path, "basics", "good", LONG_BODY)
    write_article(tmp_path, "basics", "good", LONG_BODY.replace("Heading", "Dup"))  # same file
    write_article(tmp_path, "tax", "short", "too short")
    write_article(tmp_path, "crypto", "wrong-cat", LONG_BODY)
    (tmp_path / "basics" / "broken.md").write_text("no front matter", encoding="utf-8")
    (tmp_path / "basics" / "missing.md").write_text("---\nid: missing\n---\nbody", encoding="utf-8")
    # Category in front matter doesn't match folder, plus a duplicate id
    (tmp_path / "tax" / "mismatch.md").write_text(
        FRONT.format(id="good", category="basics").replace("beginner", "expert") + LONG_BODY,
        encoding="utf-8",
    )

    result = load_articles(tmp_path, ["basics", "tax"], ["beginner"])
    errors = "\n".join(result.errors)
    assert [a.meta.id for a in result.articles] == ["good"]
    assert "shorter than 50 words" in errors
    assert "unknown category 'crypto'" in errors
    assert "must start with '---'" in errors
    assert "title" in errors  # missing required fields
    assert "does not match folder" in errors
    assert "unknown level 'expert'" in errors
    assert "duplicate id 'good'" in errors


# --- Chunking ----------------------------------------------------------------


def test_split_sections_merges_tiny_sections() -> None:
    body = "Intro line.\n\n## A\n" + " ".join(["a"] * 40) + "\n\n## Tiny\nshort\n"
    sections = split_sections(body, default_heading="Doc")
    assert [s.heading for s in sections] == ["Doc"]
    assert "short" in sections[0].text
    assert split_sections("tiny only", "Doc")[0].heading == "Doc"


def test_window_words_overlaps() -> None:
    text = " ".join(str(i) for i in range(10))
    windows = window_words(text, max_words=4, overlap_words=1)
    assert windows[0].split() == ["0", "1", "2", "3"]
    assert windows[1].split()[0] == "3"
    assert windows[-1].split()[-1] == "9"
    assert window_words("a b", 4, 1) == ["a b"]


def test_chunk_article_keeps_metadata() -> None:
    meta = ArticleMeta(
        id="x",
        title="Example",
        category="basics",
        level="beginner",
        source_url="https://example.org",  # type: ignore[arg-type]
        source_name="Ex",
        last_reviewed=date(2026, 1, 1),
    )
    body = "## Part one\n" + " ".join(["alpha"] * 200) + "\n## Part two\n" + " ".join(["beta"] * 30)
    chunks = chunk_article(
        Article(meta=meta, body=body, path="x.md"), chunk_tokens=100, overlap=0.15
    )
    assert chunks[0].id == "x#0"
    assert {c.section for c in chunks} == {"Part one", "Part two"}
    assert all(c.source_name == "Ex" and c.token_estimate > 0 for c in chunks)
    assert len([c for c in chunks if c.section == "Part one"]) > 1


# --- Glossary ----------------------------------------------------------------


def test_glossary_loads_and_validates(tmp_path: Path) -> None:
    assert len(load_glossary(FIXTURE_KB / "glossary.yaml").terms) == 2

    path = tmp_path / "glossary.yaml"
    path.write_text(
        "terms:\n"
        "  - {term: ETF, definition: An exchange traded fund basket.}\n"
        "  - {term: etf, definition: Duplicate entry for the same term.}\n"
        "  - {term: Bad, definition: short}\n",
        encoding="utf-8",
    )
    result = load_glossary(path)
    assert [t.term for t in result.terms] == ["ETF"]
    assert len(result.errors) == 2
    assert load_glossary(tmp_path / "missing.yaml").errors


# --- BM25 --------------------------------------------------------------------


def _chunk(cid: str, text: str, category: str = "basics") -> Chunk:
    return Chunk(
        id=cid,
        article_id=cid,
        title=cid,
        section="s",
        category=category,
        level="beginner",
        source_url="https://e.org",
        source_name="E",
        text=text,
        token_estimate=10,
    )


def test_tokenizer_keeps_401k_and_drops_stopwords() -> None:
    assert tokenize("What is a 401(k) plan?") == ["401(k)", "plan"]


def test_bm25_search_ranks_filters_and_persists(tmp_path: Path) -> None:
    index = BM25Index(
        [
            _chunk("a", "roth ira withdrawals are tax free in retirement", "tax"),
            _chunk("b", "stocks represent ownership in a company"),
            _chunk("c", "bonds pay interest until maturity"),
        ]
    )
    hits = index.search("roth ira tax")
    assert hits[0].chunk.id == "a"
    assert index.search("roth", category="basics") == []
    assert index.search("the and of") == []
    assert len(index.search("company ownership interest", k=1)) == 1

    index.save(tmp_path)
    loaded = BM25Index.load(tmp_path)
    assert loaded.search("bonds maturity")[0].chunk.id == "c"

    with pytest.raises(ValueError):
        BM25Index([])


# --- Pipeline ----------------------------------------------------------------


def test_pipeline_builds_index_and_report(tmp_path: Path) -> None:
    report = run_ingestion(KB_CONFIG, FIXTURE_KB, tmp_path)
    assert report.articles == 2
    assert report.glossary_terms == 2
    assert report.by_category == {"basics": 1, "tax": 1}
    assert report.empty_categories == []
    saved = json.loads((tmp_path / "ingestion_report.json").read_text())
    assert saved["chunks"] == report.chunks
    assert (
        BM25Index.load(tmp_path).search("health savings account")[0].chunk.article_id
        == "hsa-basics"
    )


def test_pipeline_strict_and_lenient(tmp_path: Path) -> None:
    source = tmp_path / "kb"
    write_article(source, "basics", "ok", LONG_BODY)
    write_article(source, "tax", "short", "too short")

    with pytest.raises(IngestionFailed) as failure:
        run_ingestion(KB_CONFIG, source, tmp_path / "index")
    assert any("shorter" in e for e in failure.value.errors)

    report = run_ingestion(KB_CONFIG, source, tmp_path / "index", strict=False)
    assert report.articles == 1
    assert report.empty_categories == ["tax"]
    assert report.errors  # glossary missing + short article are reported

    with pytest.raises(IngestionFailed):
        run_ingestion(KB_CONFIG, tmp_path / "empty", tmp_path / "index", strict=False)
