"""HTTP rate limiting: per-client and global allowances in front of every API route.

Each rule is a token bucket (`requests` per `per_seconds`, bursting up to `requests`).
A request must fit every rule that matches it; when one is empty the request gets a 429
envelope with a Retry-After header, and no rule is charged. Expensive routes (chat runs
the LLMs, market routes reach the providers) get tighter rules in config.yaml.

This stops one client from hammering the API and caps total LLM spend. It does not stop
a large distributed flood: put nginx `limit_req` or a CDN/WAF in front for that.
State is in memory (one API process), so limits reset on restart.

Pure ASGI (not BaseHTTPMiddleware) so it stays safe for SSE streaming.
"""

from __future__ import annotations

import ipaddress
import math
import re
from collections import OrderedDict
from dataclasses import dataclass

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.config.settings import RateLimitConfig, RateLimitRule
from src.core.logging import get_logger
from src.data.resilience import clock as default_clock

log = get_logger(__name__)

GLOBAL_KEY = "*"


@dataclass
class _Bucket:
    tokens: float
    updated: float


@dataclass(frozen=True)
class _CompiledRule:
    rule: RateLimitRule
    pattern: re.Pattern[str]
    methods: frozenset[str]

    @property
    def rate(self) -> float:
        return self.rule.requests / self.rule.per_seconds

    def matches(self, method: str, path: str) -> bool:
        if self.methods and method not in self.methods:
            return False
        return self.pattern.match(path) is not None


class RateLimiter:
    """Token buckets per (rule, client). Non-blocking: `check` answers allow or wait-N-s."""

    def __init__(
        self,
        rules: list[RateLimitRule],
        *,
        max_tracked_clients: int = 10_000,
        clock: default_clock.Clock = default_clock.monotonic,
    ):
        self.rules = [
            _CompiledRule(r, re.compile(r.path), frozenset(m.upper() for m in r.methods))
            for r in rules
        ]
        self.max_tracked = max_tracked_clients
        self._clock = clock
        self._buckets: OrderedDict[tuple[str, str], _Bucket] = OrderedDict()

    def _bucket(self, rule: _CompiledRule, client: str, now: float) -> _Bucket:
        key = (rule.rule.name, GLOBAL_KEY if rule.rule.scope == "global" else client)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=float(rule.rule.requests), updated=now)
            self._buckets[key] = bucket
            # Forget the least recently seen clients so memory stays bounded.
            while len(self._buckets) > self.max_tracked:
                self._buckets.popitem(last=False)
        else:
            self._buckets.move_to_end(key)
            elapsed = max(0.0, now - bucket.updated)
            bucket.tokens = min(rule.rule.requests, bucket.tokens + elapsed * rule.rate)
            bucket.updated = now
        return bucket

    def check(self, client: str, method: str, path: str) -> tuple[float, str | None]:
        """Charge one request to every matching rule.

        Returns (0, None) when allowed, else (seconds to wait, name of the limiting rule)
        without charging anything.
        """
        now = self._clock()
        matched = [
            (rule, self._bucket(rule, client, now))
            for rule in self.rules
            if rule.matches(method, path)
        ]
        wait, limiting = 0.0, None
        for rule, bucket in matched:
            if bucket.tokens < 1:
                rule_wait = (1 - bucket.tokens) / rule.rate
                if rule_wait > wait:
                    wait, limiting = rule_wait, rule.rule.name
        if limiting is not None:
            return wait, limiting
        for _, bucket in matched:
            bucket.tokens -= 1
        return 0.0, None


def _parse_networks(
    entries: list[str],
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    return [ipaddress.ip_network(entry, strict=False) for entry in entries]


class ClientIdentifier:
    """Finds the client IP, trusting X-Forwarded-For only from a known reverse proxy."""

    def __init__(self, trusted_proxies: list[str]):
        self.trusted = _parse_networks(trusted_proxies)

    def _is_trusted(self, address: str) -> bool:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        return any(ip in network for network in self.trusted)

    def __call__(self, scope: Scope) -> str:
        client = scope.get("client")
        peer = str(client[0]) if client else "unknown"
        if not self._is_trusted(peer):
            return peer
        forwarded: bytes | None = dict(scope.get("headers", [])).get(b"x-forwarded-for")
        if not forwarded:
            return peer
        # Walk from the right: each trusted proxy appended the address it saw. The first
        # untrusted hop is the real client; anything left of it may be spoofed.
        hops = [hop.strip() for hop in forwarded.decode("latin-1").split(",") if hop.strip()]
        for hop in reversed(hops):
            if not self._is_trusted(hop):
                return hop
        return hops[0] if hops else peer


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, config: RateLimitConfig, api_prefix: str):
        self.app = app
        self.enabled = config.enabled and bool(config.rules)
        self.prefix = api_prefix.rstrip("/")
        self.limiter = RateLimiter(config.rules, max_tracked_clients=config.max_tracked_clients)
        self.identify = ClientIdentifier(config.trusted_proxies)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if (
            not self.enabled
            or scope["type"] != "http"
            or not (path == self.prefix or path.startswith(self.prefix + "/"))
        ):
            await self.app(scope, receive, send)
            return

        client = self.identify(scope)
        wait, rule = self.limiter.check(client, scope["method"], path[len(self.prefix) :] or "/")
        if rule is None:
            await self.app(scope, receive, send)
            return

        retry_after = max(1, math.ceil(wait))
        log.warning(
            "rate limited",
            extra={"client": client, "rule": rule, "path": path, "retry_after": retry_after},
        )
        response = JSONResponse(
            {
                "error": {
                    "code": "rate_limited",
                    "message": (
                        f"You're sending requests too quickly. Please wait {retry_after} "
                        "seconds and try again."
                    ),
                    "retryable": True,
                }
            },
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)
