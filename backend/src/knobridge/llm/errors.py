"""Domain errors for LLM provider failures, rendered in the standard API error shape.

Adapters translate SDK exceptions into these by HTTP status, so callers never depend on a
vendor SDK. Messages are ours: the provider's own message is dropped because it can echo
part of the API key. No error uses 401, which the panel reads as "your session ended".
"""

from __future__ import annotations

from http import HTTPStatus
from typing import cast

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


class ToolsUnsupportedError(ProviderRequestError):
    """The provider refused a request with tools because the model cannot call them."""

    code = "provider_tools_unsupported"

    def __init__(self, *, provider: str, status: int) -> None:
        super().__init__("The model does not support tool calls.", provider=provider, status=status)


def tools_refused(status: int, error_body: object) -> bool:
    """Whether a 400 or 404 refused the request because of its tools: the error body's
    ``param``, ``code`` or ``message`` names them (OpenAI: 400 with ``param`` ``tools``;
    OpenRouter: 404 when no endpoint of the model takes tools).

    Only classifies the refusal: the text itself is never repeated or logged.
    """
    if status not in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
        return False
    if not isinstance(error_body, dict):
        return False
    body = cast(dict[str, object], error_body)
    nested = body.get("error")
    if isinstance(nested, dict):
        body = cast(dict[str, object], nested)
    return any(
        isinstance(value, str) and "tool" in value.lower()
        for value in (body.get("param"), body.get("code"), body.get("message"))
    )


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


def stream_error(error_type: str | None, provider: str) -> LLMProviderError:
    """The domain error for an error event received in the middle of a stream.

    The HTTP status was already 200 by then, so the provider's error type (``rate_limit_error``,
    ``overloaded_error``, ``invalid_request_error``...) is all there is to classify it. Unknown
    or missing types count as the provider failing on its side.
    """
    kind = (error_type or "").lower()
    if "rate_limit" in kind or "quota" in kind:
        return ProviderRateLimitError(
            "The provider rate limit or quota was exceeded.", provider=provider
        )
    if "auth" in kind or "permission" in kind:
        return ProviderAuthError("The provider rejected the API key.", provider=provider)
    if "invalid_request" in kind or "not_found" in kind:
        return ProviderRequestError("The provider rejected the request.", provider=provider)
    return ProviderUnavailableError("The provider failed while answering.", provider=provider)


class EmbeddingsNotSupportedError(LLMProviderError):
    """The credential's provider has no embeddings API (Anthropic)."""

    code = "provider_embeddings_unsupported"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY

    def __init__(self, provider: str) -> None:
        super().__init__("The provider does not offer embeddings.", provider=provider)


class EmbeddingResponseError(LLMProviderError):
    """The provider answered 200 with fewer or more vectors than texts sent."""

    code = "embedding_invalid_response"

    def __init__(self, *, provider: str, expected: int, received: int) -> None:
        super().__init__("The provider returned an invalid embedding response.", provider=provider)
        self.details = {"provider": provider, "expected": expected, "received": received}


class EmbeddingDimensionError(LLMProviderError):
    """A vector came back with another dimension than the index stores (wrong model)."""

    code = "embedding_dimension_mismatch"

    def __init__(self, *, provider: str, expected: int, received: int) -> None:
        super().__init__(
            f"The embedding model returned vectors of dimension {received}; "
            f"the index stores {expected}.",
            provider=provider,
        )
        self.details = {"provider": provider, "expected": expected, "received": received}
