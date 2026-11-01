"""Application container: long-lived objects built once at startup and shared by requests."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import Settings
from src.core.services.market.factory import build_http_client, build_market_service
from src.core.services.market.market_data_service import MarketDataService
from src.data.db.session import create_db_engine, create_session_factory
from src.web_app.auth.google_client import AuthlibGoogleClient, GoogleOAuthClient
from src.web_app.auth.session_tokens import SessionTokenService


@dataclass
class AppContainer:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    http_client: httpx.AsyncClient
    market: MarketDataService
    google: GoogleOAuthClient
    session_tokens: SessionTokenService

    @classmethod
    def build(cls, settings: Settings) -> AppContainer:
        engine = create_db_engine(settings)
        http_client = build_http_client(settings)
        return cls(
            settings=settings,
            engine=engine,
            session_factory=create_session_factory(engine),
            http_client=http_client,
            market=build_market_service(settings, http_client),
            google=AuthlibGoogleClient(settings),
            session_tokens=SessionTokenService(
                settings.session_secret.get_secret_value(), settings.auth.session_ttl_hours
            ),
        )

    async def aclose(self) -> None:
        await self.http_client.aclose()
        self.engine.dispose()
