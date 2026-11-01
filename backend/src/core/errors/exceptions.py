"""Application error hierarchy.

Every error carries a stable `code`, a user-safe `message`, and whether the client
may retry. The web layer turns these into the {error: {code, message, retryable}}
envelope.
"""

from __future__ import annotations


class AppError(Exception):
    code: str = "internal_error"
    status_code: int = 500
    retryable: bool = False

    def __init__(self, message: str = "Something went wrong.", *, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class ValidationFailed(AppError):
    code = "validation_failed"
    status_code = 422


class NotAuthenticated(AppError):
    code = "not_authenticated"
    status_code = 401


class Forbidden(AppError):
    code = "forbidden"
    status_code = 403


class NotFound(AppError):
    code = "not_found"
    status_code = 404


class ConfigurationError(AppError):
    code = "not_configured"
    status_code = 503


# --- Provider errors -------------------------------------------------------


class ProviderError(AppError):
    """Base for failures talking to an external data provider."""

    code = "provider_error"
    status_code = 502
    retryable = True

    def __init__(self, provider: str, message: str):
        super().__init__(f"{provider}: {message}")
        self.provider = provider


class ProviderUnavailable(ProviderError):
    """Timeout, connection failure or 5xx. Worth retrying."""

    code = "provider_unavailable"


class ProviderRateLimited(ProviderError):
    """HTTP 429 or a provider-specific throttle notice. Worth retrying after backoff."""

    code = "provider_rate_limited"


class ProviderAuthError(ProviderError):
    """401/403: bad or missing key. Never retried."""

    code = "provider_auth_error"
    retryable = False


class ProviderBadResponse(ProviderError):
    """Other 4xx or an unparseable / empty payload. Not retried."""

    code = "provider_bad_response"
    retryable = False


class CircuitOpen(ProviderError):
    """The provider is temporarily skipped after repeated failures."""

    code = "provider_circuit_open"


class UnknownSymbol(AppError):
    code = "unknown_symbol"
    status_code = 404

    def __init__(self, symbols: list[str], suggestions: list[str] | None = None):
        joined = ", ".join(symbols)
        message = f"We couldn't find {joined}. Check the ticker spelling (US stocks and ETFs only)."
        if suggestions:
            message += f" Did you mean {' or '.join(suggestions)}?"
        super().__init__(message)
        self.symbols = symbols
        self.suggestions = suggestions or []
