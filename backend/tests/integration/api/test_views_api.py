"""APIs behind the Portfolio, Market, Goals and Learn views (PF, MD, GL, KB-08)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from src.core.services.market.market_data_service import SymbolCheck
from src.core.services.risk_questionnaire import QUESTIONS
from src.data.db.models import Goal, User
from src.data.db.repositories.portfolio_repository import HoldingInput, PortfolioRepository
from src.rag.catalog import ArticleCatalog
from src.rag.ingestion.article_loader import load_articles
from tests.conftest import make_settings
from tests.unit.agents.test_agents import make_kb

API = "/api/v1"
FIXTURE_KB = Path(__file__).parents[2] / "fixtures" / "kb"
FUTURE = (date.today() + timedelta(days=5 * 365)).isoformat()


def container(client: TestClient) -> Any:
    return client.app.state.container  # type: ignore[attr-defined]


# --- Risk questionnaire (GL-01) ----------------------------------------------------------


def test_risk_questionnaire_sets_the_profile(signed_in: TestClient) -> None:
    questions = signed_in.get(f"{API}/me/risk-questionnaire").json()["questions"]
    assert [q["id"] for q in questions] == [q.id for q in QUESTIONS]

    answers = {q["id"]: q["options"][-1]["id"] for q in questions}
    body = signed_in.post(f"{API}/me/risk-questionnaire", json={"answers": answers}).json()
    assert body["result"]["risk_profile"] == "aggressive"
    assert body["me"]["profile"]["risk_profile"] == "aggressive"
    assert body["me"]["profile"]["risk_answers"] == answers

    bad = signed_in.post(f"{API}/me/risk-questionnaire", json={"answers": {"horizon": "a"}})
    assert bad.status_code == 422 and "every question" in bad.json()["error"]["message"]


# --- Goals (GL-02 to GL-04) -----------------------------------------------------------------


def test_goal_lifecycle_with_projections(signed_in: TestClient) -> None:
    assert signed_in.get(f"{API}/goals").json() == {"goals": []}
    goal = {
        "type": "house",
        "name": " Starter home ",
        "target_amount": 60000,
        "target_date": FUTURE,
        "current_savings": 10000,
        "monthly_contribution": 500,
    }
    created = signed_in.post(f"{API}/goals", json=goal)
    assert created.status_code == 201
    saved = created.json()
    assert saved["name"] == "Starter home" and saved["risk_profile"] == "moderate"  # no profile yet
    assert len(saved["projection"]["scenarios"]) == 3 and saved["projection_error"] is None

    updated = signed_in.put(
        f"{API}/goals/{saved['id']}",
        json={**goal, "monthly_contribution": 900, "risk_profile": "conservative"},
    ).json()
    assert updated["monthly_contribution"] == 900 and updated["risk_profile"] == "conservative"
    assert [g["id"] for g in signed_in.get(f"{API}/goals").json()["goals"]] == [saved["id"]]

    past = signed_in.post(f"{API}/goals", json={**goal, "target_date": "2001-01-01"})
    assert past.status_code == 422 and "future" in past.json()["error"]["message"]

    assert signed_in.delete(f"{API}/goals/{saved['id']}").status_code == 204
    assert signed_in.delete(f"{API}/goals/{saved['id']}").status_code == 404


def test_projection_endpoint_for_the_live_slider(signed_in: TestClient) -> None:
    body = {
        "target_amount": 40000,
        "target_date": FUTURE,
        "monthly_contribution": 250,
        "risk_profile": "aggressive",
    }
    low = signed_in.post(f"{API}/goals/project", json=body).json()
    high = signed_in.post(f"{API}/goals/project", json={**body, "monthly_contribution": 900}).json()
    assert low["example_allocation"]["risk_profile"] == "aggressive"

    def expected(response: dict[str, Any]) -> float:
        scenarios = response["projection"]["scenarios"]
        return float(next(s["final_value"] for s in scenarios if s["scenario"] == "expected"))

    assert expected(high) > expected(low)


def test_saved_goal_whose_date_passed_still_lists(signed_in: TestClient) -> None:
    with container(signed_in).session_factory() as db:
        user = db.query(User).one()
        db.add(
            Goal(
                user_id=user.id,
                type="other",
                name="Old",
                target_amount=1,
                target_date=date(2020, 1, 1),
                current_savings=0,
                monthly_contribution=0,
                risk_profile="moderate",
            )
        )
        db.commit()
    goals = signed_in.get(f"{API}/goals").json()["goals"]
    assert goals[0]["projection"] is None and "future" in goals[0]["projection_error"]


def test_goals_are_private(tmp_path: Path, client_for) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(tmp_path, auth={"mode": "guest"})
    alice: TestClient = client_for(settings)
    bob: TestClient = client_for(settings)
    alice.post(f"{API}/auth/guest")
    bob.post(f"{API}/auth/guest")
    goal = alice.post(
        f"{API}/goals", json={"type": "other", "target_amount": 100, "target_date": FUTURE}
    ).json()
    assert bob.get(f"{API}/goals").json() == {"goals": []}
    assert (
        bob.put(
            f"{API}/goals/{goal['id']}",
            json={"type": "other", "target_amount": 1, "target_date": FUTURE},
        ).status_code
        == 404
    )
    assert bob.delete(f"{API}/goals/{goal['id']}").status_code == 404


# --- Portfolios (PF-01 to PF-07) -------------------------------------------------------------


def seed_sample(client: TestClient) -> str:
    with container(client).session_factory() as db:
        sample = PortfolioRepository(db).upsert_sample(
            "Three-Fund Starter",
            "A simple mix.",
            [HoldingInput("VTI", 10, 200, "etf"), HoldingInput("BND", 5, None, "bond_etf")],
        )
        db.commit()
        return sample.id


def test_portfolio_lifecycle_and_analysis(signed_in: TestClient) -> None:
    sample_id = seed_sample(signed_in)
    body = {
        "name": "My mix",
        "holdings": [
            {"symbol": "aapl", "quantity": 10, "cost_basis": 150},
            {"symbol": "VTI", "quantity": 5, "asset_class": "etf"},
        ],
    }
    created = signed_in.post(f"{API}/portfolios", json=body)
    assert created.status_code == 201
    mine = created.json()
    assert [h["symbol"] for h in mine["holdings"]] == ["AAPL", "VTI"] and not mine["is_sample"]

    listed = signed_in.get(f"{API}/portfolios").json()["portfolios"]
    assert [(p["id"], p["is_sample"]) for p in listed] == [(mine["id"], False), (sample_id, True)]

    analysis = signed_in.get(f"{API}/portfolios/{mine['id']}/analysis?range=6M").json()
    assert analysis["total_value"] > 0 and analysis["benchmark"]["range"] == "6M"
    assert analysis["performance"][0]["portfolio"] == 100 and len(analysis["performance"]) > 20
    assert analysis["freshness"]
    assert signed_in.get(f"{API}/portfolios/{sample_id}/analysis").status_code == 200

    replaced = signed_in.put(
        f"{API}/portfolios/{mine['id']}",
        json={**body, "name": "Renamed", "holdings": body["holdings"][:1]},
    )
    assert replaced.json()["name"] == "Renamed" and len(replaced.json()["holdings"]) == 1

    # Samples are read-only.
    assert signed_in.put(f"{API}/portfolios/{sample_id}", json=body).status_code == 403
    assert signed_in.delete(f"{API}/portfolios/{sample_id}").status_code == 403
    assert signed_in.delete(f"{API}/portfolios/{mine['id']}").status_code == 204
    assert signed_in.get(f"{API}/portfolios/{mine['id']}").status_code == 404


def test_unknown_tickers_are_rejected_with_suggestions(signed_in: TestClient) -> None:
    async def validate(symbols: list[str]) -> SymbolCheck:
        return SymbolCheck(unknown=["APPL", "ZZZZ"], suggestions={"APPL": ["AAPL"]})

    container(signed_in).market.validate_symbols = validate
    response = signed_in.post(
        f"{API}/portfolios", json={"name": "Typos", "holdings": [{"symbol": "APPL", "quantity": 1}]}
    )
    assert response.status_code == 422
    assert response.json()["error"]["message"] == (
        "We couldn't find APPL (did you mean AAPL?), ZZZZ. US stocks and ETFs only."
    )


def test_csv_import_returns_rows_to_review(signed_in: TestClient) -> None:
    parsed = signed_in.post(
        f"{API}/portfolios/import",
        json={"content": "Symbol,Quantity,Cost Basis\nAAPL,3,150\nbad!,1,\n"},
    ).json()
    assert parsed["holdings"] == [
        {"symbol": "AAPL", "quantity": 3, "cost_basis": 150, "asset_class": None}
    ]
    assert parsed["errors"] == ["Row 3: 'bad!' isn't a valid ticker."]


def test_portfolios_are_private(tmp_path: Path, client_for) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(tmp_path, auth={"mode": "guest"})
    alice: TestClient = client_for(settings)
    bob: TestClient = client_for(settings)
    alice.post(f"{API}/auth/guest")
    bob.post(f"{API}/auth/guest")
    mine = alice.post(
        f"{API}/portfolios", json={"name": "A", "holdings": [{"symbol": "VTI", "quantity": 1}]}
    ).json()
    assert bob.get(f"{API}/portfolios").json() == {"portfolios": []}
    for method in ("get", "delete"):
        assert getattr(bob, method)(f"{API}/portfolios/{mine['id']}").status_code == 404
    assert bob.get(f"{API}/portfolios/{mine['id']}/analysis").status_code == 404


# --- Market (UI-05, MD-08, MD-09) ----------------------------------------------------------


def test_market_view_routes(signed_in: TestClient) -> None:
    movers = signed_in.get(f"{API}/market/movers?limit=3").json()
    assert len(movers["gainers"]) == 3 and len(movers["losers"]) == 3
    sectors = signed_in.get(f"{API}/market/sectors").json()["sectors"]
    assert sectors and {"sector", "symbol", "price"} <= set(sectors[0]["sector"])
    found = signed_in.get(f"{API}/market/symbols?q=apple").json()
    assert found["results"][0]["symbol"] == "AAPL"
    indicators = signed_in.get(f"{API}/market/indicators/AAPL").json()["indicators"]
    assert indicators["symbol"] == "AAPL" and indicators["sma_50"] is not None
    assert signed_in.get(f"{API}/market/symbols?q=").status_code == 422


# --- Learn (KB-08) --------------------------------------------------------------------------


def with_kb(client: TestClient) -> TestClient:
    kb = make_kb()
    kb.catalog = ArticleCatalog(load_articles(FIXTURE_KB, [], []).articles)
    container(client).knowledge_base = kb
    return client


def test_learn_routes(signed_in: TestClient) -> None:
    assert signed_in.get(f"{API}/kb/articles").status_code == 503  # no KB loaded yet
    client = with_kb(signed_in)

    listing = client.get(f"{API}/kb/articles").json()
    assert {a["id"] for a in listing["articles"]} == {"compound-growth", "hsa-basics"}
    assert listing["categories"] == [
        {"id": "basics", "label": "Basics", "count": 1},
        {"id": "tax", "label": "Tax", "count": 1},
    ]
    assert listing["levels"] == ["beginner", "intermediate", "advanced"]
    assert [
        a["id"] for a in client.get(f"{API}/kb/articles?q=health+savings").json()["articles"]
    ] == ["hsa-basics"]
    assert client.get(f"{API}/kb/articles?category=basics&q=health").json()["articles"] == []

    article = client.get(f"{API}/kb/articles/hsa-basics").json()
    assert article["category_label"] == "Tax" and article["body_md"].strip() and article["summary"]
    assert article["reading_minutes"] >= 1 and article["related"] == []  # nothing shared
    assert client.get(f"{API}/kb/articles/nope").status_code == 404

    glossary = client.get(f"{API}/kb/glossary?q=roth").json()
    assert glossary["total"] == 2 and [t["term"] for t in glossary["terms"]] == ["Roth IRA"]
    assert client.get(f"{API}/kb/glossary/what%20is%20a%20roth%20ira").json()["term"] == "Roth IRA"
    assert client.get(f"{API}/kb/glossary/zebra").status_code == 404
