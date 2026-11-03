"""Pure helpers behind the Goals, Portfolio and Learn views."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from src.core.domain.market import Bar
from src.core.domain.risk import RiskProfile
from src.core.errors import ValidationFailed
from src.core.services.portfolio_analytics import indexed_performance
from src.core.services.risk_questionnaire import (
    MAX_SCORE,
    QUESTIONS,
    profile_for_score,
    score_answers,
)
from src.rag.catalog import ArticleCatalog, category_label, reading_minutes, summarize
from src.rag.ingestion.article_loader import load_articles
from src.rag.models import Article, ArticleMeta
from src.utils.holdings_csv import MAX_ROWS, parse_holdings_csv

FIXTURE_KB = Path(__file__).parents[2] / "fixtures" / "kb"


# --- Risk questionnaire (GL-01) -------------------------------------------------------


def answers(option: str) -> dict[str, str]:
    return {q.id: option for q in QUESTIONS}


def test_questionnaire_shape() -> None:
    assert 5 <= len(QUESTIONS) <= 7  # GL-01
    assert 3 * len(QUESTIONS) == MAX_SCORE
    assert all([o.points for o in q.options] == [0, 1, 2, 3] for q in QUESTIONS)


@pytest.mark.parametrize(
    ("option", "profile"),
    [
        ("a", RiskProfile.CONSERVATIVE),
        ("b", RiskProfile.CONSERVATIVE),
        ("c", RiskProfile.MODERATE),
        ("d", RiskProfile.AGGRESSIVE),
    ],
)
def test_scoring(option: str, profile: RiskProfile) -> None:
    result = score_answers(answers(option))
    assert result.risk_profile is profile and result.max_score == MAX_SCORE


def test_score_boundaries() -> None:
    assert profile_for_score(6) is RiskProfile.CONSERVATIVE
    assert profile_for_score(7) is RiskProfile.MODERATE
    assert profile_for_score(12) is RiskProfile.MODERATE
    assert profile_for_score(13) is RiskProfile.AGGRESSIVE


def test_scoring_rejects_incomplete_or_invalid_answers() -> None:
    partial = answers("a")
    partial.pop("horizon")
    with pytest.raises(ValidationFailed, match="every question"):
        score_answers(partial)
    with pytest.raises(ValidationFailed, match="isn't an option"):
        score_answers({**answers("a"), "horizon": "z"})
    with pytest.raises(ValidationFailed, match="Unknown questions: bogus"):
        score_answers({**answers("a"), "bogus": "a"})


# --- Holdings CSV (PF-01) ---------------------------------------------------------------


def test_csv_with_broker_headers_and_row_errors() -> None:
    text = (
        "﻿Ticker,Shares,Avg Cost,Type\n"
        'aapl,10,"$1,500.25",Stock\n'
        "VTI,5,,etf\n"
        "BRK.B,2,300,mystery\n"
        "\n"
        "not a ticker,1,1,\n"
        "MSFT,0,1,\n"
        "NVDA,abc,1,\n"
        "QQQ,1,-5,\n"
    )
    result = parse_holdings_csv(text)
    assert [(h.symbol, h.quantity, h.cost_basis, h.asset_class) for h in result.holdings] == [
        ("AAPL", 10, 1500.25, "stock"),
        ("VTI", 5, None, "etf"),
        ("BRK.B", 2, 300, None),
    ]
    assert result.errors == [
        "Row 5: 'not a ticker' isn't a valid ticker.",
        "Row 6: quantity must be more than 0.",
        "Row 7: quantity and cost basis must be numbers.",
        "Row 8: cost basis can't be negative.",
    ]


def test_csv_file_level_problems() -> None:
    assert parse_holdings_csv("").errors == ["The file is empty."]
    assert "missing: quantity" in parse_holdings_csv("symbol,price\nAAPL,1\n").errors[0]
    assert parse_holdings_csv("x" * 1_000_001).errors == ["The file is larger than 1 MB."]
    many = "symbol,quantity\n" + "AAPL,1\n" * (MAX_ROWS + 5)
    result = parse_holdings_csv(many)
    assert len(result.holdings) == MAX_ROWS
    assert result.errors == [f"Only the first {MAX_ROWS} rows were read."]


# --- Benchmark line (PF-05) ---------------------------------------------------------------


def bars(closes: list[float], start: date = date(2026, 1, 1)) -> list[Bar]:
    return [
        Bar(
            t=datetime.combine(start + timedelta(days=i), datetime.min.time(), UTC),
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1,
        )
        for i, c in enumerate(closes)
    ]


def test_indexed_performance_rebases_and_thins() -> None:
    series = [(date(2026, 1, 1) + timedelta(days=i), 1000.0 + 10 * i) for i in range(10)]
    points = indexed_performance(series, bars([50.0 + i for i in range(1, 10)], date(2026, 1, 2)))
    assert points[0].portfolio == 100 and points[0].benchmark == 100  # first shared date
    assert points[-1].date == date(2026, 1, 10)
    assert points[-1].portfolio == round(1090 / 1010 * 100, 2)

    thinned = indexed_performance(series, bars([50.0 + i for i in range(10)]), max_points=4)
    assert len(thinned) <= 5 and thinned[-1].date == date(2026, 1, 10)
    assert indexed_performance(series[:1], bars([1.0])) == []


# --- Article catalog (KB-08) ---------------------------------------------------------------


def catalog() -> ArticleCatalog:
    return ArticleCatalog(load_articles(FIXTURE_KB, [], []).articles)


def test_catalog_filters_and_searches() -> None:
    kb = catalog()
    assert len(kb) == 2 and kb.category_counts() == {"basics": 1, "tax": 1}
    assert [a.meta.id for a in kb.search(category="tax")] == ["hsa-basics"]
    assert kb.search(level="no-such-level") == []
    assert [a.meta.id for a in kb.search("health savings")] == ["hsa-basics"]
    assert kb.search("health compounding") == []  # every term must match
    assert kb.get("hsa-basics") is not None and kb.get("missing") is None


def _article(id: str, category: str, level: str, tags: list[str], words: int = 50) -> Article:
    meta = ArticleMeta(
        id=id,
        title=id.replace("-", " ").title(),
        category=category,
        level=level,
        source_url="https://example.com",  # type: ignore[arg-type]
        source_name="Example",
        last_reviewed=date(2026, 10, 1),
        tags=tags,
    )
    return Article(meta=meta, body="word " * words, path=f"{id}.md")


def test_related_articles_rank_shared_tags_then_category_then_level() -> None:
    kb = ArticleCatalog(
        [
            _article("wash-sale", "tax", "intermediate", ["wash sale", "capital losses"]),
            _article("loss-harvesting", "tax", "advanced", ["capital losses", "harvesting"]),
            _article("ira-basics", "tax", "beginner", ["retirement"]),
            _article("hsa", "tax", "intermediate", ["health"]),
            _article("sale-signs", "stocks", "beginner", ["wash sale"]),
            _article("unrelated", "bonds", "beginner", ["yield"]),
        ]
    )
    # Shared tags first (incl. another category); same-category ties prefer the same or
    # next level up; nothing in common is never suggested.
    assert [a.meta.id for a in kb.related("wash-sale", limit=4)] == [
        "loss-harvesting",
        "sale-signs",
        "hsa",
        "ira-basics",
    ]
    assert kb.related("missing") == []
    assert reading_minutes("word " * 30) == 1 and reading_minutes("word " * 1000) == 5


def test_summary_and_labels() -> None:
    body = "# Title\n\n## Section\n\nFirst real paragraph " + "word " * 60
    assert summarize(body).startswith("First real paragraph") and summarize(body).endswith("…")
    assert summarize("# Only a heading") == ""
    assert category_label("funds_etfs") == "Funds & ETFs"
    assert category_label("new_topic") == "New topic"
