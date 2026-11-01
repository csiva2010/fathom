"""Liveness plus database, knowledge index and provider status."""

from __future__ import annotations

from fastapi import APIRouter

from src import __version__
from src.core.config import resolve_path
from src.data.db.session import ping
from src.rag.keyword.bm25_index import INDEX_FILENAME
from src.web_app.dependencies import ContainerDep
from src.web_app.schemas.health import HealthResponse, ProviderHealth

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Health and provider status")
def health(container: ContainerDep) -> HealthResponse:
    settings = container.settings
    db_ok = ping(container.engine)
    index_ok = (resolve_path(settings.kb.index_dir) / INDEX_FILENAME).exists()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=__version__,
        env=settings.app.env,
        auth_mode=settings.auth.mode,
        database=db_ok,
        knowledge_index=index_ok,
        providers=[
            ProviderHealth(name=p.name, configured=p.configured, circuit=p.breaker_state.value)
            for p in container.market.provider_status()
        ],
    )
