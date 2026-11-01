"""Market and health routes through the app. No provider keys, so data comes from mock."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.rag.ingestion.pipeline import run_ingestion
from tests.conftest import FIXTURES, make_settings

API = "/api/v1"


def test_health_reports_components(client: TestClient, settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    body = client.get(f"{API}/health").json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["knowledge_index"] is False
    assert body["auth_mode"] == "stub"
    assert {p["name"]: p["configured"] for p in body["providers"]} == {
        "alpaca": False,
        "alpha_vantage": False,
    }

    run_ingestion(settings.kb, FIXTURES / "kb", tmp_path / "index")
    assert client.get(f"{API}/health").json()["knowledge_index"] is True


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get(f"{API}/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["x-request-id"] == "abc123"
    assert len(client.get(f"{API}/health").headers["x-request-id"]) == 32


def test_quotes_with_freshness_and_unknown_symbols(signed_in: TestClient) -> None:
    body = signed_in.get(f"{API}/market/quotes", params={"symbols": "aapl,VOO,ZZZZ"}).json()
    assert [q["quote"]["symbol"] for q in body["quotes"]] == ["AAPL", "VOO"]
    assert body["quotes"][0]["freshness"]["status"] == "mock"
    assert body["unknown_symbols"] == ["ZZZZ"]


def test_quotes_all_unknown_is_404_and_bad_input_is_422(signed_in: TestClient) -> None:
    missing = signed_in.get(f"{API}/market/quotes", params={"symbols": "ZZZZ"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "unknown_symbol"

    bad = signed_in.get(f"{API}/market/quotes", params={"symbols": "$$$"})
    assert bad.status_code == 422


def test_overview_returns_index_cards(signed_in: TestClient) -> None:
    indices = signed_in.get(f"{API}/market/overview").json()["indices"]
    assert [i["index"]["id"] for i in indices] == ["SPX", "IXIC", "DJI"]
    assert all(i["freshness"]["status"] == "mock" for i in indices)


def test_history_and_range_validation(signed_in: TestClient) -> None:
    body = signed_in.get(f"{API}/market/history/VOO", params={"range": "3M"}).json()
    assert body["history"]["range"] == "3M"
    assert body["history"]["bars"]

    assert signed_in.get(f"{API}/market/history/VOO", params={"range": "2W"}).status_code == 422
    unavailable = signed_in.get(f"{API}/market/history/ZZZZ")
    assert unavailable.status_code == 502
    assert unavailable.json()["error"]["retryable"] is True


def test_news_falls_back_to_empty_state(signed_in: TestClient) -> None:
    body = signed_in.get(f"{API}/market/news", params={"symbols": "AAPL", "limit": 5}).json()
    assert body["items"] == []
    assert body["freshness"]["status"] == "mock"


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    response = client.get(f"{API}/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_cache_warm_up_runs_at_startup_when_enabled(client_for, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(tmp_path, market={"warm_cache": {"on_startup": True}})
    client = client_for(settings)
    assert client.get(f"{API}/health").status_code == 200
    # Shutdown cancels the warm-up task cleanly whether or not it finished.
