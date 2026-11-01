from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.config import BACKEND_ROOT, Settings, resolve_path
from src.core.domain.market import Bar
from src.core.errors import UnknownSymbol, ValidationFailed
from src.core.logging import configure_logging
from src.core.logging.context import request_id_var, user_id_var
from src.core.logging.formatters import JsonFormatter
from src.core.services.market.ranges import trim_to_sessions
from src.core.services.market.symbols import MAX_SYMBOLS, normalise_symbol, normalise_symbols
from tests.conftest import make_settings

# --- Settings ----------------------------------------------------------------


def test_settings_load_yaml_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.app.api_prefix == "/api/v1"
    assert [i.proxy_symbol for i in settings.market.indices] == ["SPY", "QQQ", "DIA"]
    assert "tax" in settings.kb.categories


def test_env_overrides_nested_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH__MODE", "stub")
    monkeypatch.setenv("MARKET__ALPACA__FEED", "iex")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "id")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.auth.mode == "stub"
    assert settings.market.alpaca.feed == "iex"
    assert settings.alpaca_configured
    assert not settings.alpha_vantage_configured
    assert not settings.google_configured


def test_local_urls_derive_from_web_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_PORT", "5174")
    monkeypatch.setenv("API_PORT", "8001")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.api_port == 8001
    assert settings.app.frontend_url == "http://localhost:5174"
    assert settings.app.cors_origins == ["http://localhost:5174"]
    assert settings.auth.google_redirect_uri == (
        "http://localhost:5174/api/v1/auth/google/callback"
    )


def test_explicit_urls_win_over_port_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_PORT", "5174")
    monkeypatch.setenv("APP__FRONTEND_URL", "https://finance.example.com")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.app.cors_origins == ["https://finance.example.com"]
    assert settings.auth.google_redirect_uri.startswith("https://finance.example.com/api/v1")


def test_production_refuses_stub_auth_and_default_secret(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="stub"):
        make_settings(tmp_path, app={"env": "production"}, auth={"mode": "stub"})
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        make_settings(
            tmp_path, app={"env": "production"}, auth={"mode": "google"}, session_secret="change-me"
        )
    ok = make_settings(tmp_path, app={"env": "production"}, auth={"mode": "google"})
    assert ok.app.env == "production"


def test_resolve_path() -> None:
    assert resolve_path("data/kb") == BACKEND_ROOT / "data/kb"
    assert resolve_path("/abs/path") == Path("/abs/path")


# --- Logging -----------------------------------------------------------------


def test_json_formatter_includes_context_extra_and_exceptions() -> None:
    token_r = request_id_var.set("req-1")
    token_u = user_id_var.set("user-1")
    try:
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.getLogger("t").makeRecord(
                "t", logging.ERROR, __file__, 1, "hello %s", ("world",), exc_info=True
            )
            import sys

            record.exc_info = sys.exc_info()
        record.provider = "alpaca"
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token_r)
        user_id_var.reset(token_u)

    assert payload["msg"] == "hello world"
    assert payload["request_id"] == "req-1"
    assert payload["user_id"] == "user-1"
    assert payload["provider"] == "alpaca"
    assert "ValueError" in payload["exc"]


def test_configure_logging_plain_and_json(tmp_path: Path) -> None:
    configure_logging(make_settings(tmp_path, logging={"level": "DEBUG", "json": False}))
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert not isinstance(root.handlers[0].formatter, JsonFormatter)
    configure_logging(make_settings(tmp_path))
    assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)


# --- Symbols and ranges ------------------------------------------------------


@pytest.mark.parametrize("raw", ["aapl", " VOO ", "BRK.B", "BF-B"])
def test_valid_symbols(raw: str) -> None:
    assert normalise_symbol(raw) == raw.strip().upper()


@pytest.mark.parametrize("raw", ["", "1ABC", "TOOLONGX", "AA PL", "$$"])
def test_invalid_symbols(raw: str) -> None:
    with pytest.raises(ValidationFailed):
        normalise_symbol(raw)


def test_normalise_symbols_dedupes_and_limits() -> None:
    assert normalise_symbols("aapl,AAPL, voo,") == ["AAPL", "VOO"]
    with pytest.raises(ValidationFailed):
        normalise_symbols(" , ")
    with pytest.raises(ValidationFailed):
        normalise_symbols([f"A{i}" for i in range(MAX_SYMBOLS + 1)])


def test_trim_to_sessions() -> None:
    def bar(day: int) -> Bar:
        return Bar(
            t=datetime(2026, 10, day, 15, tzinfo=UTC), open=1, high=1, low=1, close=1, volume=1
        )

    bars = [bar(27), bar(28), bar(28), bar(29)]
    assert trim_to_sessions(bars, 2) == bars[1:]
    assert trim_to_sessions(bars, None) == bars
    assert trim_to_sessions([], 1) == []


def test_unknown_symbol_message() -> None:
    assert "ZZZ" in UnknownSymbol(["ZZZ"]).message


def test_guest_mode_is_allowed_in_production(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, app={"env": "production"}, auth={"mode": "guest"})
    assert settings.auth.mode == "guest"
