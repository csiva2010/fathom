"""FastAPI dependencies shared by routers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from src.core.config import Settings
from src.core.services.market.market_data_service import MarketDataService
from src.data.db.session import session_scope
from src.web_app.container import AppContainer


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


def get_settings_dep(container: Annotated[AppContainer, Depends(get_container)]) -> Settings:
    return container.settings


def get_db(container: Annotated[AppContainer, Depends(get_container)]) -> Iterator[Session]:
    yield from session_scope(container.session_factory)


def get_market(container: Annotated[AppContainer, Depends(get_container)]) -> MarketDataService:
    return container.market


ContainerDep = Annotated[AppContainer, Depends(get_container)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DbDep = Annotated[Session, Depends(get_db)]
MarketDep = Annotated[MarketDataService, Depends(get_market)]
