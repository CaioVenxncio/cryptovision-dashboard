"""Provider exception hierarchy.

Every message is written to be safe for display: no credentials, headers or
raw request objects are included.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for failures while retrieving data from an external provider."""


class MissingApiKeyError(ProviderError):
    """No API key is configured."""


class AuthenticationError(ProviderError):
    """The provider rejected the credentials (HTTP 401 or 403)."""


class RateLimitError(ProviderError):
    """The provider rate limit was exceeded (HTTP 429) and retries were exhausted."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailableError(ProviderError):
    """Network failure, timeout or HTTP 5xx after retries were exhausted."""


class ProviderRequestError(ProviderError):
    """The provider rejected the request (HTTP 4xx other than 401, 403 and 429)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ResponseSchemaError(ProviderError):
    """The response body is not valid JSON or does not match the expected schema."""
