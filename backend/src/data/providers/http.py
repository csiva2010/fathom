"""Shared HTTP call that maps transport/status failures onto ProviderError types."""

from __future__ import annotations

from typing import Any

import httpx

from src.core.errors import (
    ProviderAuthError,
    ProviderBadResponse,
    ProviderRateLimited,
    ProviderUnavailable,
)


async def get_json(
    client: httpx.AsyncClient,
    provider: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    try:
        response = await client.get(url, params=params, headers=headers)
    except httpx.TimeoutException as error:
        raise ProviderUnavailable(provider, "request timed out") from error
    except httpx.TransportError as error:
        raise ProviderUnavailable(
            provider, f"connection failed ({type(error).__name__})"
        ) from error

    status = response.status_code
    if status == 429:
        raise ProviderRateLimited(provider, "rate limit reached")
    if status in (401, 403):
        raise ProviderAuthError(provider, "credentials rejected")
    if status >= 500:
        raise ProviderUnavailable(provider, f"server error {status}")
    if status >= 400:
        raise ProviderBadResponse(provider, f"request rejected ({status})")

    try:
        return response.json()
    except ValueError as error:
        raise ProviderBadResponse(provider, "response was not valid JSON") from error
