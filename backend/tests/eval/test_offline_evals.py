"""The golden sets in offline mode (INN-02): CI fails if a metric drops below its floor.

Offline means the real knowledge base with keyword retrieval, rule routing, template
answers and mock market data: no network, no keys, deterministic. The live run with real
models and the faithfulness judge is `python -m scripts.run_evals --live`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.rag.models import Citation
from src.workflow.state import AgentName, FinalAnswer
from tests.eval.harness import (
    OFFLINE_FLOORS,
    FaithfulnessJudge,
    SuiteReport,
    build_system,
    check_answer,
    eval_answers,
    load_golden,
    run_suites,
    source_text,
    write_reports,
)
from tests.fakes import gateway, structured


@pytest.fixture(scope="module")
def reports(tmp_path_factory: pytest.TempPathFactory) -> dict[str, SuiteReport]:
    """Every suite, run once per module (its own event loop: the fixture outlives tests)."""
    scratch = tmp_path_factory.mktemp("eval")

    async def run() -> dict[str, SuiteReport]:
        async with httpx.AsyncClient() as client:
            system = build_system(False, scratch, client)
            return {r.suite: r for r in await run_suites(system)}

    return asyncio.run(run())


def explain(report: SuiteReport) -> str:
    return "\n" + report.to_markdown()


@pytest.mark.parametrize("suite", sorted(OFFLINE_FLOORS))
def test_offline_suite_meets_its_floors(reports: dict[str, SuiteReport], suite: str) -> None:
    report = reports[suite]
    assert not report.below_floor(OFFLINE_FLOORS[suite]), explain(report)


def test_golden_sets_are_well_formed(reports: dict[str, SuiteReport]) -> None:
    from src.core.config import Settings, resolve_path
    from src.rag.ingestion.article_loader import load_articles

    kb = Settings(_env_file=None).kb  # type: ignore[call-arg]
    article_ids = {
        a.meta.id
        for a in load_articles(resolve_path(kb.source_dir), kb.categories, kb.levels).articles
    }
    retrieval = load_golden("retrieval")["cases"]
    answers = load_golden("answers")["cases"]
    referenced = {a for c in retrieval for a in c.get("expected", [])}
    referenced |= {a for c in answers for a in c.get("sources", [])}
    assert referenced <= article_ids, referenced - article_ids
    assert len(retrieval) >= 40 and len(load_golden("routing")["cases"]) >= 40
    ids = [
        c["id"] for name in ("retrieval", "routing", "answers") for c in load_golden(name)["cases"]
    ]
    assert len(ids) == len(set(ids))
    agents = {a for c in load_golden("routing")["cases"] for a in c.get("agents", [])}
    assert agents == {a.value for a in AgentName}  # every agent is covered
    assert reports["answers"].metrics["cases"] == sum(1 for c in answers if c.get("offline", True))


def test_reports_render(reports: dict[str, SuiteReport], tmp_path: Path) -> None:
    markdown, raw = write_reports(list(reports.values()), tmp_path)
    text = markdown.read_text()
    assert "## Retrieval (offline)" in text and "| hit@5 |" in text and "| finance_qa |" in text
    assert raw.read_text().startswith("[")


async def test_faithfulness_judge_scores_cited_answers(tmp_path: Path) -> None:
    gw, model = gateway(
        structured(
            "FaithfulnessVerdict",
            claims=[
                {"claim": "Index funds track an index.", "supported": True},
                {"claim": "They always beat active funds.", "supported": False},
            ],
        ),
        structured("FaithfulnessVerdict", claims=[]),
    )
    judge = FaithfulnessJudge(gw)
    async with httpx.AsyncClient() as client:
        system = build_system(False, tmp_path, client)
    report = await eval_answers(
        system.answer_graph,
        "offline",
        chunks=system.chunks,
        judge=judge,
        case_ids=["ans-01", "ans-06"],
    )
    assert report.metrics["faithfulness"] == pytest.approx(0.75)  # (0.5 + 1.0) / 2
    assert report.cases[0].detail["unsupported"] == ["They always beat active funds."]
    graded = model.calls[0][-1].text
    assert '<data source="sources">' in graded and "[1] " in graded  # cited chunk text


def test_answer_checks_and_source_text() -> None:
    citation = Citation(
        article_id="a", title="A", section="S", source_name="n", source_url="https://x"
    )
    final = FinalAnswer(answer_md="You should buy it now.", citations=[citation])
    checks, _ = check_answer(
        {"q": "q", "kind": "redirect", "disclaimer": True, "no_sources": True}, final
    )
    assert checks == {"no_advice": False, "kind": False, "no_sources": False, "disclaimer": False}

    class FakeChunk:
        article_id, section, text = "a", "S", "Chunk text."

    chunks: Any = [FakeChunk()]
    assert source_text(final, chunks) == "[1] A / S\nChunk text."
