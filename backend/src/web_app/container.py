"""Application container: long-lived objects built once at startup and shared by requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import Settings
from src.core.llm import LLMGateway, build_llm_gateway
from src.core.services.market.factory import build_http_client, build_market_service
from src.core.services.market.market_data_service import MarketDataService
from src.data.db.session import create_db_engine, create_session_factory
from src.rag.knowledge_base import KnowledgeBase, load_knowledge_base
from src.web_app.auth.google_client import AuthlibGoogleClient, GoogleOAuthClient
from src.web_app.auth.session_tokens import SessionTokenService
from src.workflow.context import DbContextLoader
from src.workflow.factory import create_workflow


@dataclass
class AppContainer:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    http_client: httpx.AsyncClient
    market: MarketDataService
    google: GoogleOAuthClient
    session_tokens: SessionTokenService
    llm: LLMGateway = field(default_factory=lambda: LLMGateway([]))
    knowledge_base: KnowledgeBase | None = None
    workflow: Any = None  # compiled LangGraph; see src/workflow/graph.py

    @classmethod
    def build(cls, settings: Settings) -> AppContainer:
        engine = create_db_engine(settings)
        session_factory = create_session_factory(engine)
        http_client = build_http_client(settings)
        market = build_market_service(settings, http_client)
        llm = build_llm_gateway(settings)
        knowledge_base = load_knowledge_base(settings)
        # In-memory checkpoints until the chat endpoint lands with the SQLite checkpointer.
        workflow = create_workflow(
            settings.workflow,
            llm,
            knowledge_base,
            market,
            DbContextLoader(session_factory),
            checkpointer=InMemorySaver(),
        )
        return cls(
            settings=settings,
            engine=engine,
            session_factory=session_factory,
            http_client=http_client,
            market=market,
            google=AuthlibGoogleClient(settings),
            session_tokens=SessionTokenService(
                settings.session_secret.get_secret_value(), settings.auth.session_ttl_hours
            ),
            llm=llm,
            knowledge_base=knowledge_base,
            workflow=workflow,
        )

    async def aclose(self) -> None:
        await self.http_client.aclose()
        self.engine.dispose()
