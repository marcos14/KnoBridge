"""Domain errors for LLM provider failures, rendered in the standard API error shape.

Adapters translate SDK exceptions into these by HTTP status, so callers never depend on a
vendor SDK. Messages are ours: the provider's own message is dropped because it can echo
part of the API key. No error uses 401, which the panel reads as "your session ended".
"""

from __future__ import annotations

from http import HTTPStatus

from knobridge.core.errors import KnoBridgeError


class LLMProviderError(KnoBridgeError):
    code = "provider_error"
    status_code = HTTPStatus.BAD_GATEWAY

    def __init__(self, message: str, *, provider: str, status: int | None = None) -> None:
        super().__init__(message, details={"provider": provider, "status": status})
        self.provider = provider
        self.status = status


class ProviderAuthError(LLMProviderError):
    """The provider refused the API key (invalid, revoked or without permission)."""

    code = "provider_auth_failed"


class ProviderRateLimitError(LLMProviderError):
    """Rate limit or quota exhausted at the provider."""

    code = "provider_rate_limited"
    status_code = HTTPStatus.TOO_MANY_REQUESTS


class ProviderUnavailableError(LLMProviderError):
    """Provider unreachable, timed out or failing on its side (5xx)."""

    code = "provider_unavailable"
    status_code = HTTPStatus.SERVICE_UNAVAILABLE


class ProviderRequestError(LLMProviderError):
    """The provider rejected the request itself (unknown model, invalid parameters)."""

    code = "provider_request_failed"


def error_for_status(status: int, provider: str) -> LLMProviderError:
    """The domain error for an HTTP error status returned by ``provider``."""
    if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
        return ProviderAuthError(
            "The provider rejected the API key.", provider=provider, status=status
        )
    if status == HTTPStatus.TOO_MANY_REQUESTS:
        return ProviderRateLimitError(
            "The provider rate limit or quota was exceeded.", provider=provider, status=status
        )
    if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return ProviderUnavailableError(
            "The provider is unavailable.", provider=provider, status=status
        )
    return ProviderRequestError(
        "The provider rejected the request.", provider=provider, status=status
    )


def connection_error(provider: str) -> ProviderUnavailableError:
    """The domain error when ``provider`` could not be reached or timed out."""
    return ProviderUnavailableError("Could not reach the provider.", provider=provider)
