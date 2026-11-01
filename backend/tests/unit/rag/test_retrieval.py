from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from src.core.config.settings import KnowledgeBaseConfig, RerankerConfig, RetrievalConfig
from src.rag.embeddings import LangChainEmbedder, build_embedders
from src.rag.glossary import Glossary, normalise_term
from src.rag.ingestion.pipeline import embed_chunks, run_ingestion
from src.rag.keyword.bm25_index import BM25Index
from src.rag.knowledge_base import load_knowledge_base
from src.rag.models import Chunk, GlossaryTerm
from src.rag.reranker import CrossEncoderReranker, LexicalReranker, build_reranker
from src.rag.retriever import HybridRetriever, reciprocal_rank_fusion
from src.rag.vector_store import ChromaVectorStore
from tests.conftest import make_settings
from tests.fakes import FixedReranker, HashEmbedder

FIXTURE_KB = Path(__file__).parents[2] / "fixtures" / "kb"
CONFIG = RetrievalConfig(top_n=3)


def chunk(cid: str, text: str, *, category: str = "basics", level: str = "beginner") -> Chunk:
    article = cid.split("#")[0]
    return Chunk(
        id=cid,
        article_id=article,
        title=article.replace("-", " ").title(),
        section="Overview",
        category=category,
        level=level,
        source_url=f"https://example.org/{article}",
        source_name="Example",
        text=text,
        token_estimate=len(text.split()),
    )


CHUNKS = [
    chunk(
        "roth-ira#0",
        "A Roth IRA is funded with after-tax money; qualified withdrawals are tax-free.",
        category="tax",
    ),
    chunk(
        "roth-ira#1",
        "Roth IRA contributions can be withdrawn at any time.",
        category="tax",
        level="intermediate",
    ),
    chunk("bonds#0", "A bond is a loan to a government or company that pays interest."),
    chunk("etf#0", "An ETF is a fund that trades on an exchange like a stock."),
]


# --- Fusion and retriever ----------------------------------------------------


def test_reciprocal_rank_fusion_rewards_agreement() -> None:
    scores = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], k=60)
    assert max(scores, key=lambda key: scores[key]) == "b"
    assert set(scores) == {"a", "b", "c"}


async def test_keyword_only_search_returns_citations() -> None:
    retriever = HybridRetriever(BM25Index(CHUNKS), LexicalReranker(0.5), CONFIG)
    result = await retriever.search("What is a Roth IRA?")
    assert result.found and result.mode == "keyword"
    assert result.chunks[0].chunk.article_id == "roth-ira"
    # Two chunks of the same article section collapse into one citation.
    assert [c.article_id for c in result.citations] == ["roth-ira"]
    assert len(result.citations_per_chunk()) == len(result.chunks)
    assert retriever.chunk_count == 4


async def test_threshold_gives_no_context() -> None:
    retriever = HybridRetriever(BM25Index(CHUNKS), LexicalReranker(0.5), CONFIG)
    assert not (await retriever.search("quantum chromodynamics lecture")).found
    assert not (await retriever.search("   ")).found
    # A term matches but the reranker scores it below the threshold.
    low = HybridRetriever(BM25Index(CHUNKS), FixedReranker({"bonds": 0.1}), CONFIG)
    assert not (await low.search("bond interest")).found


async def test_category_filter_and_level_boost() -> None:
    retriever = HybridRetriever(
        BM25Index(CHUNKS), FixedReranker({"roth-ira": 0.8}), RetrievalConfig(level_boost=0.5)
    )
    result = await retriever.search("Roth IRA withdrawn", category="tax", level="intermediate")
    assert {hit.chunk.category for hit in result.chunks} == {"tax"}
    assert result.chunks[0].chunk.id == "roth-ira#1"  # boosted by the user's level


async def test_hybrid_search_and_embedder_fallback(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma")
    primary, fallback = HashEmbedder("kb_primary", fail=True), HashEmbedder("kb_fallback")
    vectors = await embed_chunks(fallback, CHUNKS, batch_size=2)
    assert store.rebuild("kb_fallback", CHUNKS, vectors) == 4
    assert store.count("kb_fallback") == 4 and store.count("kb_missing") == 0

    retriever = HybridRetriever(
        BM25Index(CHUNKS),
        LexicalReranker(0.3),
        CONFIG,
        vector_store=store,
        embedders=[primary, fallback],
    )
    result = await retriever.search("exchange traded fund", category="basics")
    assert result.mode == "hybrid:kb_fallback"
    assert result.chunks[0].chunk.article_id == "etf"

    # Every embedder fails (or its collection was never built): BM25 alone answers.
    broken = HybridRetriever(
        BM25Index(CHUNKS),
        LexicalReranker(0.3),
        CONFIG,
        vector_store=store,
        embedders=[HashEmbedder("kb_missing")],
    )
    assert (await broken.search("bond interest")).mode == "keyword"


def test_vector_store_rejects_mismatched_lengths(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ChromaVectorStore(tmp_path).rebuild("kb_test", CHUNKS, [[0.1]])


async def test_embed_chunks_checks_vector_count() -> None:
    class Short(HashEmbedder):
        async def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return []

    with pytest.raises(ValueError):
        await embed_chunks(Short(), CHUNKS, batch_size=10)


# --- Rerankers ---------------------------------------------------------------


def test_lexical_reranker_scores_term_overlap() -> None:
    reranker = LexicalReranker(0.5)
    assert reranker.score("Roth IRA", CHUNKS[:1]) == [1.0]
    assert reranker.score("the of", CHUNKS[:1]) == [0.0]
    assert build_reranker(RerankerConfig(kind="lexical")).min_score == 0.5


def test_cross_encoder_uses_model_and_sigmoid(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCrossEncoder:
        def __init__(self, name: str):
            self.name = name

        def predict(self, pairs: list[tuple[str, str]], activation_fn: object) -> list[float]:
            assert activation_fn is not None
            return [0.9 for _ in pairs]

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=FakeCrossEncoder)
    )
    reranker = build_reranker(RerankerConfig(kind="cross_encoder", cross_encoder_min_score=0.02))
    assert isinstance(reranker, CrossEncoderReranker)
    assert reranker.warm_up()
    assert reranker.score("q", CHUNKS[:2]) == [0.9, 0.9]
    assert reranker.score("q", []) == []
    assert reranker.min_score == 0.02


def test_cross_encoder_falls_back_to_lexical(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        def __init__(self, name: str):
            raise OSError("weights not found")

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=Broken)
    )
    reranker = CrossEncoderReranker("missing-model", 0.02, LexicalReranker(0.4))
    assert reranker.score("Roth IRA", CHUNKS[:1]) == [1.0]
    assert reranker.min_score == 0.4
    assert not reranker.warm_up()


# --- Glossary ----------------------------------------------------------------


def make_glossary() -> Glossary:
    return Glossary(
        [
            GlossaryTerm(
                term="ETF",
                definition="A fund that trades on an exchange.",
                aliases=["exchange-traded fund"],
            ),
            GlossaryTerm(
                term="Bond", definition="A loan to a government or company.", related=["Yield"]
            ),
            GlossaryTerm(
                term="Price-to-earnings ratio",
                definition="Price divided by earnings per share.",
                aliases=["P/E ratio"],
            ),
        ]
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("What is an ETF?", "ETF"),
        ("explain exchange-traded fund", "ETF"),
        ("what are bonds?", "Bond"),
        ("What does P/E ratio mean?", "Price-to-earnings ratio"),
        ("define the bond", "Bond"),
    ],
)
def test_glossary_lookup(query: str, expected: str) -> None:
    term = make_glossary().lookup(query)
    assert term is not None and term.term == expected


def test_glossary_misses_suggestions_and_search() -> None:
    glossary = make_glossary()
    assert glossary.lookup("What is a quasar?") is None
    assert glossary.lookup("?") is None
    assert glossary.suggest("bnd") == ["Bond"]
    assert [t.term for t in glossary.search("exchange")] == ["ETF"]
    assert len(glossary.search("")) == 3
    assert len(glossary) == 3
    assert normalise_term("  What's a  Roth IRA? ") == "roth ira"


# --- Pipeline, embedders and loading ------------------------------------------


def test_pipeline_builds_vector_collections_and_reports_failures(tmp_path: Path) -> None:
    config = KnowledgeBaseConfig(categories=["basics", "tax"], chunk_tokens=120)
    report = run_ingestion(
        config,
        FIXTURE_KB,
        tmp_path / "index",
        embedders=[HashEmbedder("kb_good"), HashEmbedder("kb_bad", fail=True)],
        vector_dir=tmp_path / "chroma",
        embed_batch_size=2,
    )
    assert report.vector_collections == {"kb_good": report.chunks}
    assert report.vector_skipped and report.vector_skipped[0].startswith("kb_bad")
    # Re-running rebuilds instead of duplicating (KB-07).
    again = run_ingestion(
        config,
        FIXTURE_KB,
        tmp_path / "index",
        embedders=[HashEmbedder("kb_good")],
        vector_dir=tmp_path / "chroma",
    )
    assert again.vector_collections == {"kb_good": report.chunks}


def test_build_embedders_skips_missing_keys(tmp_path: Path) -> None:
    kb = {
        "embeddings": [
            {
                "provider": "gemini",
                "model": "gemini-embedding-2",
                "collection": "kb_gemini",
                "requests_per_minute": 90,
            },
            {"provider": "openai", "model": "text-embedding-3-small", "collection": "kb_openai"},
        ]
    }
    assert build_embedders(make_settings(tmp_path, kb=kb)) == []
    both = build_embedders(make_settings(tmp_path, kb=kb, gemini_api_key="g", openai_api_key="o"))
    assert [e.collection for e in both] == ["kb_gemini", "kb_openai"]
    assert [e.requests_per_minute for e in both] == [90, None]
    assert all(isinstance(e, LangChainEmbedder) for e in both)


async def test_langchain_embedder_delegates() -> None:
    from langchain_core.embeddings import DeterministicFakeEmbedding

    embedder = LangChainEmbedder("kb_fake", DeterministicFakeEmbedding(size=8))
    assert len(await embedder.embed_query("hi")) == 8
    assert len(await embedder.embed_documents(["a", "b"])) == 2


async def test_load_knowledge_base_builds_missing_index(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        kb={
            "source_dir": str(FIXTURE_KB),
            "index_dir": str(tmp_path / "index"),
            "vector_dir": str(tmp_path / "chroma"),
            "categories": ["basics", "tax"],
        },
    )
    kb = load_knowledge_base(settings, embedders=[], reranker=LexicalReranker(0.3))
    assert kb is not None
    assert len(kb.glossary) == 2
    assert (await kb.retriever.search("health savings account")).found

    # With a populated vector store and an embedder, vector search is wired in.
    store = ChromaVectorStore(tmp_path / "chroma")
    embedder = HashEmbedder("kb_test")
    chunks = kb.retriever._index.chunks
    store.rebuild("kb_test", chunks, await embed_chunks(embedder, chunks, 10))
    hybrid = load_knowledge_base(settings, embedders=[embedder], reranker=LexicalReranker(0.3))
    assert hybrid is not None
    assert (await hybrid.retriever.search("compound interest")).mode == "hybrid:kb_test"


def test_load_knowledge_base_without_source_returns_none(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        kb={
            "source_dir": str(tmp_path / "empty"),
            "index_dir": str(tmp_path / "index"),
            "categories": [],
        },
    )
    assert load_knowledge_base(settings, embedders=[]) is None


# --- Embedding quota handling --------------------------------------------------


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


async def test_sliding_window_never_exceeds_limit() -> None:
    from src.data.resilience.sliding_window import SlidingWindowLimiter

    fake = FakeTime()
    limiter = SlidingWindowLimiter(100, clock=fake.clock, sleep=fake.sleep)
    await limiter.acquire(64)
    await limiter.acquire(36)
    assert fake.sleeps == []
    await limiter.acquire(10)  # window full: waits for the first entry to expire
    assert fake.now == pytest.approx(60.0)
    with pytest.raises(ValueError):
        await limiter.acquire(101)
    with pytest.raises(ValueError):
        SlidingWindowLimiter(0)


def test_retry_delay_parses_rate_limit_errors() -> None:
    from src.rag.ingestion.pipeline import DEFAULT_RETRY_SECONDS, retry_delay

    gemini = RuntimeError("429 RESOURCE_EXHAUSTED ... Please retry in 28.32s.")
    assert retry_delay(gemini) == pytest.approx(29.32)
    assert retry_delay(RuntimeError("Rate limit reached")) == DEFAULT_RETRY_SECONDS
    assert retry_delay(RuntimeError("invalid api key")) is None


async def test_embed_chunks_paces_to_quota_and_retries_429() -> None:
    fake = FakeTime()
    embedder = HashEmbedder("kb_paced")
    embedder.requests_per_minute = 2
    failures = [RuntimeError("429 RESOURCE_EXHAUSTED retry in 5s")]
    original = embedder.embed_documents

    async def flaky(texts: list[str]) -> list[list[float]]:
        if failures:
            raise failures.pop()
        return await original(texts)

    embedder.embed_documents = flaky  # type: ignore[method-assign]
    vectors = await embed_chunks(
        embedder, CHUNKS, batch_size=64, clock=fake.clock, sleep=fake.sleep
    )
    assert len(vectors) == 4
    # Batches shrink to the quota (2), the 429 waits 6 s, and the second batch waits
    # for the window to roll over.
    assert fake.sleeps[0] == pytest.approx(6.0)
    assert fake.now >= 60.0


async def test_embed_chunks_gives_up_after_retries() -> None:
    fake = FakeTime()
    embedder = HashEmbedder("kb_down")

    async def always_429(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("429 Too Many Requests")

    embedder.embed_documents = always_429  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await embed_chunks(embedder, CHUNKS, batch_size=2, clock=fake.clock, sleep=fake.sleep)
    assert len(fake.sleeps) == 3
