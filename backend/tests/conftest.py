"""Shared fixtures: isolated settings, an in-file SQLite DB, fake OAuth and a test client."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from src.core.config import Settings
from src.core.config.settings import get_settings
from src.core.errors import NotAuthenticated
from src.core.services.market.factory import build_market_service
from src.data.db.base import Base
from src.data.db.repositories.user_repository import GoogleIdentity
from src.data.db.session import create_db_engine, create_session_factory
from src.web_app.auth.session_tokens import SessionTokenService
from src.web_app.container import AppContainer
from src.web_app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Settings for tests: stub auth, temp DB and index, no provider keys."""
    base: dict[str, object] = {
        "app": {"env": "test", "frontend_url": "http://localhost:5173"},
        "auth": {"mode": "stub"},
        "database": {"url": f"sqlite:///{tmp_path / 'test.db'}"},
        "logging": {"level": "WARNING", "json": True},
        "kb": {
            "source_dir": str(FIXTURES / "kb"),
            "index_dir": str(tmp_path / "index"),
            "categories": ["basics", "tax"],
        },
        "workflow": {"checkpoint_path": str(tmp_path / "checkpoints.db")},
        # Off so suites that make many requests are not throttled; see test_rate_limit.py.
        "rate_limit": {"enabled": False},
        "session_secret": "test-secret-0123456789-abcdefghijklmnopqrstuvwxyz",
        "google_client_id": "",
        "google_client_secret": "",
        "alpaca_api_key_id": "",
        "alpaca_api_secret_key": "",
        "alpha_vantage_api_key": "",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


class FakeGoogleClient:
    """Stands in for Google: redirects to a fake consent URL and returns a fixed identity."""

    def __init__(self) -> None:
        self.identity: GoogleIdentity | None = GoogleIdentity(
            sub="google-123", email="ada@example.com", name="Ada Lovelace", avatar_url=None
        )

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> Response:
        return RedirectResponse(f"https://accounts.example/consent?redirect_uri={redirect_uri}")

    async def fetch_identity(self, request: Request) -> GoogleIdentity:
        if self.identity is None:
            raise NotAuthenticated("Google sign-in failed: invalid_grant")
        return self.identity


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def fake_google() -> FakeGoogleClient:
    return FakeGoogleClient()


def build_container(settings: Settings, google: FakeGoogleClient) -> AppContainer:
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    http_client = httpx.AsyncClient()
    return AppContainer(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        http_client=http_client,
        market=build_market_service(settings, http_client),
        google=google,
        session_tokens=SessionTokenService(settings.session_secret.get_secret_value(), 12),
    )


@pytest.fixture
def client_for(fake_google: FakeGoogleClient):  # type: ignore[no-untyped-def]
    """Factory: build a TestClient for given settings."""
    clients: list[TestClient] = []

    def _make(settings: Settings) -> TestClient:
        app = create_app(settings, build_container(settings, fake_google))
        client = TestClient(app, base_url="http://localhost:5173")
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(client_for, settings: Settings) -> TestClient:  # type: ignore[no-untyped-def]
    return client_for(settings)  # type: ignore[no-any-return]


@pytest.fixture
def signed_in(client: TestClient) -> TestClient:
    """A client that has completed the stub sign-in and holds a session cookie."""
    response = client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert response.status_code == 303
    return client
