"""Small JSON-over-HTTP client with timeouts and bounded retries."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from cryptovision.providers.errors import (
    AuthenticationError,
    ProviderError,
    ProviderRequestError,
    ProviderUnavailableError,
    RateLimitError,
    ResponseSchemaError,
)

logger = logging.getLogger(__name__)

RETRYABLE_SERVER_STATUSES = frozenset({500, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff.

    Attempt `n` (0-based) waits `min(backoff_max, backoff_base * 2**n)`, scaled
    by a random jitter factor in [0.5, 1.0]. A server `Retry-After` value
    replaces the computed delay. When `Retry-After` exceeds
    `max_retry_after_seconds` the client fails immediately instead of blocking.
    """

    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30.0
    max_retry_after_seconds: float = 60.0

    def backoff(self, attempt: int, jitter: float) -> float:
        delay = min(self.backoff_max_seconds, self.backoff_base_seconds * 2**attempt)
        return delay * (0.5 + 0.5 * jitter)


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Parse a `Retry-After` header (delta-seconds or HTTP-date) into seconds."""
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    now = now or datetime.now(UTC)
    return max(0.0, (moment - now).total_seconds())


class HttpJsonClient:
    """Performs GET requests and returns decoded JSON.

    Retries only on timeouts, connection errors, HTTP 429 and HTTP 5xx, at most
    `retry_policy.max_retries` times. Authentication and other client errors
    fail immediately.
    """

    def __init__(
        self,
        base_url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
        retry_policy: RetryPolicy | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._timeout = timeout_seconds
        self._retry = retry_policy or RetryPolicy()
        self._session = session or requests.Session()
        self._sleep = sleep
        self._jitter = jitter

    def __repr__(self) -> str:
        # Headers can hold credentials, so they are deliberately omitted.
        return f"{type(self).__name__}(base_url={self._base_url!r})"

    def get_json(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        url = f"{self._base_url}/{path.lstrip('/')}"
        attempts = self._retry.max_retries + 1

        for attempt in range(attempts):
            outcome = self._attempt(url, path, params)
            if isinstance(outcome, _Success):
                return outcome.payload
            if attempt == attempts - 1:
                raise outcome
            delay = self._delay_for(outcome, attempt)
            logger.warning(
                "Request to %s failed (%s); retry %d of %d in %.1fs",
                path,
                outcome,
                attempt + 1,
                self._retry.max_retries,
                delay,
            )
            self._sleep(delay)

        raise AssertionError("unreachable")  # pragma: no cover

    def _delay_for(self, error: ProviderError, attempt: int) -> float:
        if isinstance(error, RateLimitError) and error.retry_after_seconds is not None:
            return error.retry_after_seconds
        return self._retry.backoff(attempt, self._jitter())

    def _attempt(
        self, url: str, path: str, params: Mapping[str, str] | None
    ) -> ProviderError | _Success:
        """Perform one request. Returns retryable errors; raises non-retryable ones."""
        try:
            response = self._session.get(
                url, params=params, headers=self._headers, timeout=self._timeout
            )
        except requests.Timeout:
            return ProviderUnavailableError(f"Request to {path} timed out.")
        except requests.ConnectionError:
            return ProviderUnavailableError(f"Could not connect to the provider ({path}).")
        except requests.RequestException as exc:
            raise ProviderUnavailableError(
                f"Request to {path} failed ({type(exc).__name__})."
            ) from None
        return self._interpret(response, path)

    def _interpret(self, response: requests.Response, path: str) -> ProviderError | _Success:
        status = response.status_code
        if 200 <= status < 300:
            try:
                return _Success(response.json())
            except ValueError:
                raise ResponseSchemaError(f"Response from {path} is not valid JSON.") from None
        if status in (401, 403):
            raise AuthenticationError(
                f"The provider rejected the API key (HTTP {status}). "
                "Check COINGECKO_API_KEY and that it is a Demo plan key."
            )
        if status == 429:
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            error = RateLimitError(
                f"Rate limit exceeded for {path} (HTTP 429).", retry_after_seconds=retry_after
            )
            if retry_after is not None and retry_after > self._retry.max_retry_after_seconds:
                raise error
            return error
        if status in RETRYABLE_SERVER_STATUSES:
            return ProviderUnavailableError(f"Provider error for {path} (HTTP {status}).")
        raise ProviderRequestError(f"Request to {path} was rejected (HTTP {status}).")


@dataclass(frozen=True)
class _Success:
    payload: Any
