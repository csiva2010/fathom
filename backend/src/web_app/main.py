"""FastAPI application factory.

Run locally:  uvicorn src.web_app.main:app --reload   (from the backend/ folder)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src import __version__
from src.core.config import Settings, get_settings, resolve_path
from src.core.logging import configure_logging, get_logger
from src.core.services.market.warmup import sample_symbols, warm_cache
from src.data.providers.mock.seed_loader import SeedData
from src.web_app.container import AppContainer
from src.web_app.errors.handlers import register_error_handlers
from src.web_app.middleware.origin_check import OriginCheckMiddleware
from src.web_app.middleware.request_context import RequestContextMiddleware
from src.web_app.routers import auth, conversations, goals, health, kb, market, me, portfolios
from src.web_app.schemas.errors import ErrorEnvelope

log = get_logger(__name__)


def create_app(settings: Settings | None = None, container: AppContainer | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container or AppContainer.build(settings)
        await app.state.container.start()
        warmup: asyncio.Task[dict[str, int]] | None = None
        if settings.market.warm_cache.on_startup:
            symbols = sample_symbols(
                SeedData(resolve_path(settings.seed.dir)), [settings.market.benchmark_symbol]
            )
            warmup = asyncio.create_task(warm_cache(app.state.container.market, symbols))
        log.info(
            "api started",
            extra={
                "env": settings.app.env,
                "auth_mode": settings.auth.mode,
                "version": __version__,
            },
        )
        try:
            yield
        finally:
            if warmup is not None:
                warmup.cancel()
                with suppress(asyncio.CancelledError):
                    await warmup
            await app.state.container.aclose()

    app = FastAPI(
        title=settings.app.name,
        version=__version__,
        description="Educational multi-agent finance assistant. Not investment advice.",
        lifespan=lifespan,
        docs_url=f"{settings.app.api_prefix}/docs",
        openapi_url=f"{settings.app.api_prefix}/openapi.json",
    )

    # Middleware runs outermost-last-added: request context wraps everything.
    allowed_origins = list({*settings.app.cors_origins, settings.app.frontend_url})
    app.add_middleware(OriginCheckMiddleware, allowed_origins=allowed_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    # Short-lived signed cookie that holds OAuth state/nonce/PKCE verifier during sign-in.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        session_cookie="fa_oauth",
        max_age=600,
        same_site="lax",
        https_only=settings.auth.cookie_secure,
    )
    app.add_middleware(RequestContextMiddleware)

    register_error_handlers(app)

    prefix = settings.app.api_prefix
    # Document the shared error envelope on every protected route (DOC-03).
    error_responses: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorEnvelope} for status in (401, 404, 422, 502)
    }
    app.include_router(health.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(me.router, prefix=prefix, responses=error_responses)
    app.include_router(market.router, prefix=prefix, responses=error_responses)
    app.include_router(conversations.router, prefix=prefix, responses=error_responses)
    app.include_router(portfolios.router, prefix=prefix, responses=error_responses)
    app.include_router(goals.router, prefix=prefix, responses=error_responses)
    app.include_router(kb.router, prefix=prefix, responses=error_responses)
    return app


app = create_app()
