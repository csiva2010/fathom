from __future__ import annotations

import httpx
import pytest
import respx

from src.core.errors import (
    ProviderAuthError,
    ProviderBadResponse,
    ProviderRateLimited,
    ProviderUnavailable,
)
from src.data.providers.http import get_json

URL = "https://api.example/data"


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, ProviderRateLimited),
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (500, ProviderUnavailable),
        (503, ProviderUnavailable),
        (404, ProviderBadResponse),
    ],
)
@respx.mock
async def test_status_codes_map_to_provider_errors(status: int, error: type[Exception]) -> None:
    respx.get(URL).respond(status)
    async with httpx.AsyncClient() as client:
        with pytest.raises(error):
            await get_json(client, "p", URL)


@respx.mock
async def test_timeouts_and_connection_errors_are_unavailable() -> None:
    route = respx.get(URL)
    async with httpx.AsyncClient() as client:
        route.side_effect = httpx.ReadTimeout("slow")
        with pytest.raises(ProviderUnavailable, match="timed out"):
            await get_json(client, "p", URL)
        route.side_effect = httpx.ConnectError("refused")
        with pytest.raises(ProviderUnavailable, match="connection failed"):
            await get_json(client, "p", URL)


@respx.mock
async def test_invalid_json_is_bad_response_and_valid_json_returns() -> None:
    route = respx.get(URL)
    async with httpx.AsyncClient() as client:
        route.respond(200, text="<html>")
        with pytest.raises(ProviderBadResponse):
            await get_json(client, "p", URL)
        route.respond(200, json={"ok": True})
        assert await get_json(client, "p", URL, params={"a": 1}) == {"ok": True}
