"""Application container: long-lived objects built once at startup and shared by requests."""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

import aiosqlite
import httpx
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import Settings, resolve_path
from src.core.llm import LLMGateway, build_llm_gateway
from src.core.services.market.factory import build_http_client, build_market_service
from src.core.services.market.market_data_service import MarketDataService
from src.core.services.portfolio_service import PortfolioAnalysisService
from src.data.db.session import create_db_engine, create_session_factory
from src.rag.knowledge_base import KnowledgeBase, load_knowledge_base
from src.web_app.auth.google_client import AuthlibGoogleClient, GoogleOAuthClient
from src.web_app.auth.session_tokens import SessionTokenService
from src.workflow.context import DbContextLoader
from src.workflow.factory import create_workflow
from src.workflow.state import CHECKPOINT_TYPES


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
    portfolios: PortfolioAnalysisService | None = None
    # Set by `start` unless given (tests inject their own); see src/workflow/graph.py.
    checkpointer: BaseCheckpointSaver[Any] | None = None
    workflow: Any = None
    _resources: AsyncExitStack = field(default_factory=AsyncExitStack)

    @classmethod
    def build(cls, settings: Settings) -> AppContainer:
        engine = create_db_engine(settings)
        http_client = build_http_client(settings)
        market = build_market_service(settings, http_client)
        return cls(
            settings=settings,
            engine=engine,
            session_factory=create_session_factory(engine),
            http_client=http_client,
            market=market,
            google=AuthlibGoogleClient(settings),
            session_tokens=SessionTokenService(
                settings.session_secret.get_secret_value(), settings.auth.session_ttl_hours
            ),
            llm=build_llm_gateway(settings),
            knowledge_base=load_knowledge_base(settings),
            portfolios=PortfolioAnalysisService(
                market, benchmark_symbol=settings.market.benchmark_symbol
            ),
        )

    async def start(self) -> None:
        """Open async resources: the checkpointer, then the workflow that saves to it."""
        if self.portfolios is None:
            self.portfolios = PortfolioAnalysisService(
                self.market, benchmark_symbol=self.settings.market.benchmark_symbol
            )
        if self.checkpointer is None:
            self.checkpointer = await self._open_checkpointer()
        if self.workflow is None:
            self.workflow = create_workflow(
                self.settings.workflow,
                self.llm,
                self.knowledge_base,
                self.market,
                DbContextLoader(self.session_factory),
                checkpointer=self.checkpointer,
                portfolios=self.portfolios,
            )

    async def _open_checkpointer(self) -> BaseCheckpointSaver[Any]:
        # Only our own state types may be deserialized from a checkpoint.
        serde = JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_TYPES)
        path = self.settings.workflow.checkpoint_path
        if not path:
            return InMemorySaver(serde=serde)
        file = resolve_path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(file))
        self._resources.push_async_callback(conn.close)
        saver = AsyncSqliteSaver(conn, serde=serde)
        await saver.setup()
        return saver

    async def aclose(self) -> None:
        await self._resources.aclose()
        await self.http_client.aclose()
        self.engine.dispose()
