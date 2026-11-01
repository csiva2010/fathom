"""HTTP client for the Finance Assistant REST API, authenticated with an access token."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

URL_ENV = "FINANCE_API_URL"
TOKEN_ENV = "FINANCE_API_TOKEN"
TIMEOUT_SECONDS = 30.0


class ApiError(Exception):
    """A failure to show the model as-is: the message is already user-facing."""


@dataclass(frozen=True)
class ApiConfig:
    base_url: str  # including the API prefix, e.g. https://finance.example.com/api/v1
    token: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ApiConfig:
        env = os.environ if environ is None else environ
        base_url = env.get(URL_ENV, "").strip().rstrip("/")
        token = env.get(TOKEN_ENV, "").strip()
        missing = [name for name, value in ((URL_ENV, base_url), (TOKEN_ENV, token)) if not value]
        if missing:
            raise ValueError(
                f"Set {' and '.join(missing)} in the MCP server's environment "
                "(the env block of the Claude Desktop config)."
            )
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(f"{URL_ENV} must start with http:// or https://, got {base_url!r}.")
        return cls(base_url=base_url, token=token)


class FinanceApi:
    def __init__(self, config: ApiConfig, transport: httpx.AsyncBaseTransport | None = None):
        self._base_url = config.base_url
        self._client = httpx.AsyncClient(
            base_url=config.base_url + "/",
            headers={"Authorization": f"Bearer {config.token}", "User-Agent": "fathom-mcp"},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, body: Mapping[str, Any]) -> Any:
        return await self._request("POST", path, json=body)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path.lstrip("/"), **kwargs)
        except httpx.TimeoutException as error:
            raise ApiError("The Finance Assistant API took too long to answer.") from error
        except httpx.HTTPError as error:
            raise ApiError(
                f"Couldn't reach the Finance Assistant API at {self._base_url}. "
                "Is the backend running?"
            ) from error
        if response.status_code == 401:
            raise ApiError(
                "The access token was rejected. Create a new one on the Profile page "
                "and update the Claude Desktop config."
            )
        if response.is_error:
            raise ApiError(_error_message(response))
        return response.json() if response.content else None


def _error_message(response: httpx.Response) -> str:
    """The API's error envelope message, or a generic one for non-JSON failures."""
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return f"The Finance Assistant API returned HTTP {response.status_code}."
    return str(message)
