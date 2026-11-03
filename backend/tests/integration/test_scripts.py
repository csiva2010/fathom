"""The operational scripts run end to end against temp settings."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from scripts import check_providers, export_openapi, ingest_kb, run_api, run_evals, seed_db
from src.data.db.base import Base
from src.data.db.repositories.portfolio_repository import PortfolioRepository
from src.data.db.session import create_db_engine, create_session_factory
from tests.conftest import make_settings


def test_ingest_kb_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(tmp_path)
    monkeypatch.setattr(ingest_kb, "get_settings", lambda: settings)
    assert ingest_kb.main([]) == 0
    assert '"articles": 2' in capsys.readouterr().out

    broken = make_settings(tmp_path, kb={"source_dir": str(tmp_path / "none"), "categories": []})
    monkeypatch.setattr(ingest_kb, "get_settings", lambda: broken)
    assert ingest_kb.main(["--lenient"]) == 1
    assert "Ingestion failed" in capsys.readouterr().err


def test_seed_db_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path)
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(seed_db, "get_settings", lambda: settings)

    assert seed_db.main() == 0
    assert seed_db.main() == 0  # idempotent
    session = create_session_factory(engine)()
    assert len(PortfolioRepository(session).list_samples()) == 3
    session.close()


def test_check_providers_without_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(check_providers, "get_settings", lambda: make_settings(tmp_path))
    assert check_providers.main() == 1
    out = capsys.readouterr().out
    assert "ALPHA_VANTAGE_API_KEY is not set" in out
    assert "ALPACA_API_KEY_ID" in out


@respx.mock
def test_check_providers_with_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(
        tmp_path,
        alpha_vantage_api_key="av",
        alpaca_api_key_id="id",
        alpaca_api_secret_key="secret",
    )
    monkeypatch.setattr(check_providers, "get_settings", lambda: settings)

    def av(request: httpx.Request) -> httpx.Response:
        if request.url.params["symbol"] == "SPX":
            return httpx.Response(
                200,
                json={
                    "Global Quote": {"05. price": "5800", "07. latest trading day": "2026-10-29"}
                },
            )
        return httpx.Response(200, json={"Global Quote": {}})

    respx.get("https://www.alphavantage.co/query").mock(side_effect=av)
    respx.get("https://data.alpaca.markets/v2/stocks/snapshots").respond(
        200, json={"SPY": {"latestTrade": {"p": 575.0, "t": "2026-10-30T15:00:00Z"}}}
    )

    assert check_providers.main() == 1  # IXIC/DJI unsupported, QQQ/DIA missing
    out = capsys.readouterr().out
    assert "OK   S&P 500" in out
    assert "FAIL Nasdaq Composite" in out
    assert "OK   SPY" in out
    assert "FAIL QQQ" in out

    respx.get("https://data.alpaca.markets/v2/stocks/snapshots").respond(401)
    assert check_providers.main() == 1
    assert "provider_auth_error" in capsys.readouterr().out


def test_run_api_uses_api_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(run_api, "get_settings", lambda: make_settings(tmp_path, api_port=8001))
    monkeypatch.setattr(run_api.uvicorn, "run", lambda app, **kw: calls.append({"app": app, **kw}))

    assert run_api.main(["--no-reload"]) == 0
    assert calls == [
        {"app": "src.web_app.main:app", "host": "127.0.0.1", "port": 8001, "reload": False}
    ]


def test_run_evals_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "reports"
    assert run_evals.main(["--suite", "compliance", "--out", str(out), "--gate"]) == 0
    printed = capsys.readouterr().out
    assert "## Compliance (rules)" in printed and "Report:" in printed
    assert len(list(out.glob("*-rules.md"))) == 1 and len(list(out.glob("*-rules.json"))) == 1

    # Below a floor, --gate fails the run (CI uses this).
    monkeypatch.setitem(run_evals.OFFLINE_FLOORS, "routing", {"agent_recall": 1.01})
    args = ["--suite", "routing", "--case", "rt-01", "--pause", "0.001", "--out", str(out)]
    assert run_evals.main([*args, "--gate"]) == 1
    assert "Below the offline floors" in capsys.readouterr().err
    assert run_evals.main(args) == 0  # without --gate it only reports


def test_export_openapi_script(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "openapi.json"
    assert export_openapi.main([str(target)]) == 0
    schema = json.loads(target.read_text())
    assert "TraceStepEvent" in schema["components"]["schemas"]
    assert "wrote" in capsys.readouterr().out
