from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.core.config.settings import RateLimitConfig, RateLimitRule
from src.web_app.middleware.rate_limit import ClientIdentifier, RateLimiter, RateLimitMiddleware
from tests.conftest import make_settings


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def rule(name: str, requests: int, per_seconds: float = 60, **extra: Any) -> RateLimitRule:
    return RateLimitRule(name=name, requests=requests, per_seconds=per_seconds, **extra)


# --- Limiter -----------------------------------------------------------------


def test_limiter_allows_a_burst_then_refills() -> None:
    clock = FakeClock()
    limiter = RateLimiter([rule("api", 2, per_seconds=10)], clock=clock)
    assert limiter.check("a", "GET", "/x") == (0.0, None)
    assert limiter.check("a", "GET", "/x") == (0.0, None)
    wait, limiting = limiter.check("a", "GET", "/x")
    assert limiting == "api"
    assert wait == pytest.approx(5.0)

    clock.now = 5.0
    assert limiter.check("a", "GET", "/x") == (0.0, None)


def test_limiter_keeps_clients_apart_but_shares_global_rules() -> None:
    limiter = RateLimiter(
        [rule("per_client", 1), rule("everyone", 2, scope="global")], clock=FakeClock()
    )
    assert limiter.check("a", "GET", "/x")[1] is None
    assert limiter.check("a", "GET", "/x")[1] == "per_client"
    assert limiter.check("b", "GET", "/x")[1] is None
    assert limiter.check("c", "GET", "/x")[1] == "everyone"


def test_limiter_matches_path_and_method_and_charges_nothing_when_refused() -> None:
    limiter = RateLimiter(
        [rule("api", 3), rule("chat", 1, path="/conversations/[^/]+/messages$", methods=["post"])],
        clock=FakeClock(),
    )
    assert limiter.check("a", "GET", "/conversations/c1/messages")[1] is None  # GET: api only
    assert limiter.check("a", "POST", "/conversations/c1/messages")[1] is None
    assert limiter.check("a", "POST", "/conversations/c1/messages")[1] == "chat"
    # The refused chat message did not use the last api token.
    assert limiter.check("a", "GET", "/market/quotes")[1] is None
    assert limiter.check("a", "GET", "/market/quotes")[1] == "api"


def test_limiter_forgets_least_recently_seen_clients() -> None:
    limiter = RateLimiter([rule("api", 1)], max_tracked_clients=2, clock=FakeClock())
    limiter.check("a", "GET", "/")
    limiter.check("b", "GET", "/")
    limiter.check("c", "GET", "/")  # evicts "a"
    assert limiter.check("a", "GET", "/")[1] is None
    assert limiter.check("c", "GET", "/")[1] == "api"


# --- Client identity ---------------------------------------------------------


def scope_for(peer: str | None, forwarded: str | None = None) -> dict[str, Any]:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return {"client": (peer, 1234) if peer else None, "headers": headers}


def test_client_ip_trusts_forwarded_for_only_from_a_trusted_proxy() -> None:
    identify = ClientIdentifier(["127.0.0.1", "10.0.0.0/8"])
    # Directly connected client: a forged header is ignored.
    assert identify(scope_for("203.0.113.9", "1.2.3.4")) == "203.0.113.9"
    # Through nginx: the right-most untrusted hop is the client; left of it may be spoofed.
    assert identify(scope_for("127.0.0.1", "6.6.6.6, 198.51.100.7")) == "198.51.100.7"
    assert identify(scope_for("127.0.0.1", "198.51.100.7, 10.1.2.3")) == "198.51.100.7"
    assert identify(scope_for("127.0.0.1", "10.1.2.3")) == "10.1.2.3"
    assert identify(scope_for("127.0.0.1")) == "127.0.0.1"
    assert identify(scope_for("testclient")) == "testclient"
    assert identify(scope_for(None)) == "unknown"


def test_config_rejects_bad_proxies_regexes_and_duplicate_names() -> None:
    with pytest.raises(ValueError):
        RateLimitConfig(trusted_proxies=["not-an-ip"])
    with pytest.raises(ValueError):
        rule("bad", 1, path="(")
    with pytest.raises(ValueError, match="unique"):
        RateLimitConfig(rules=[rule("api", 1), rule("api", 2)])


# --- Middleware --------------------------------------------------------------


def limited_settings(tmp_path: Path, rules: list[dict[str, Any]]) -> Any:
    return make_settings(tmp_path, rate_limit={"enabled": True, "rules": rules})


def test_middleware_returns_429_envelope_with_retry_after(tmp_path: Path, client_for) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = client_for(
        limited_settings(
            tmp_path, [{"name": "auth", "path": "/auth/", "requests": 2, "per_seconds": 60}]
        )
    )
    for _ in range(2):
        assert client.get("/api/v1/auth/config").status_code == 200
    response = client.get("/api/v1/auth/config")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.json()["error"]["retryable"] is True
    assert "x-request-id" in response.headers
    # Other routes are not covered by the rule.
    assert client.get("/api/v1/health").status_code == 200


def test_middleware_counts_clients_behind_the_proxy_separately(tmp_path: Path, client_for) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(
        tmp_path,
        rate_limit={
            "enabled": True,
            "trusted_proxies": ["127.0.0.1"],
            "rules": [{"name": "api", "requests": 1, "per_seconds": 60}],
        },
    )
    # "testclient" is not an IP, so it is never trusted: X-Forwarded-For is ignored.
    client: TestClient = client_for(settings)
    first = client.get("/api/v1/auth/config", headers={"X-Forwarded-For": "1.1.1.1"})
    second = client.get("/api/v1/auth/config", headers={"X-Forwarded-For": "2.2.2.2"})
    assert (first.status_code, second.status_code) == (200, 429)


async def test_middleware_skips_disabled_and_non_api_requests() -> None:
    calls: list[str] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        calls.append(scope["type"])

    config = RateLimitConfig(rules=[rule("api", 1)])
    middleware = RateLimitMiddleware(app, config, "/api/v1")
    for path in ("/health", "/api/v1x", "/elsewhere"):
        await middleware({"type": "http", "path": path, "method": "GET"}, None, None)  # type: ignore[arg-type]
    await middleware({"type": "lifespan"}, None, None)  # type: ignore[arg-type]

    off = RateLimitConfig(enabled=False, rules=[rule("api", 1)])
    disabled = RateLimitMiddleware(app, off, "/api/v1")
    scope = {"type": "http", "path": "/api/v1/x", "method": "GET"}
    for _ in range(3):
        await disabled(scope, None, None)  # type: ignore[arg-type]
    assert len(calls) == 7
